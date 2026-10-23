library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- =============================================================================
-- C6502_Interface  --  Rev 6 (Commodore 64)
--
-- VERA + GeoRAM 256 KB bus interface for the Commodore 64 expansion port.
-- Single bitstream:
--   make       ->  C6502_Interface.bin
--
-- I/O map:
--   IO1 $DE00-$DEFF : GeoRAM data window (one 256-byte page), external SRAM
--   IO2 $DF00-$DF1F : VERA registers, VERA_CS asserted
--   IO2 $DFFD       : VERA select latch, write != $00 selects, $00 deselects
--   IO2 $DFFE       : GeoRAM page register  (write only, 0-63)
--   IO2 $DFFF       : GeoRAM block register (write only, 0-15)
--
-- The VERA responds only while selected through $DFFD (per-cycle VERA_CS:
-- /IO2, $DF00-$DF1F, latch set, PHI2 high).  The GeoRAM window and registers
-- are always active, like the original cartridge; the latch always responds.
--
-- Every access is qualified by the C64 /IO1 and /IO2 lines.  The PLA asserts
-- them only for CPU accesses (AEC high), so VIC-II fetches, whose addresses
-- also appear on the expansion port, are ignored.  /IO1 and /IO2 already
-- decode A15-A8, so only A7-A0 are needed.
--
-- GeoRAM on an AS6C4008 (512K x 8, 55 ns), lower 256 KB used:
--   SRAM A[7:0]   = C64 A[7:0]          (direct PCB net, no FPGA pin)
--   SRAM A[13:8]  = page  register      (FPGA SRAM_PAGE[5:0])
--   SRAM A[17:14] = block register      (FPGA SRAM_BLOCK[3:0])
--   SRAM A18      = GND
--   SRAM DQ[7:0]  = data bus            (same net as FPGA D[7:0])
--   offset        = block * 16384 + page * 256 + A[7:0]
--
-- Register write timing:
--   The 6510 puts write data on the bus during PHI2 high, up to ~150 ns after
--   the rising edge.  Latch and GeoRAM registers are therefore sampled
--   SAMPLE_CLKS cycles after the synchronised PHI2 rising edge (default
--   6 x 40 ns = 240 ns, i.e. ~280-320 ns after the real edge), well inside the
--   ~490 ns PHI2-high window (PAL 0.985 MHz / NTSC 1.023 MHz).
--
-- Latch and GeoRAM registers power up at zero (VERA deselected) and are not
-- cleared by a C64 reset, like the original GeoRAM.
--
-- BRAM usage: 0 / 30 EBR.
-- =============================================================================

entity C6502_Interface is
    generic (
        SAMPLE_CLKS : positive := 6     -- CLK cycles after phi2_rise to sample D
    );
    port (
        CLK         : in    std_logic;  -- 25 MHz FPGA system clock

        -- C64 expansion port
        A           : in    std_logic_vector(7 downto 0);  -- A7-A0 (page from /IO1, /IO2)
        D           : in    std_logic_vector(7 downto 0);  -- only read (register writes)
        RNW         : in    std_logic;  -- high = read, low = write
        PHI2        : in    std_logic;
        IO1_N       : in    std_logic;  -- C64 /IO1, $DE00-$DEFF CPU access (active low)
        IO2_N       : in    std_logic;  -- C64 /IO2, $DF00-$DFFF CPU access (active low)

        -- Bus control output
        VERA_CS     : out   std_logic;  -- VERA chip-select (active low)

        -- External SRAM (GeoRAM) -- 13 pins
        SRAM_PAGE   : out   std_logic_vector(5 downto 0);   -- SRAM A[13:8]
        SRAM_BLOCK  : out   std_logic_vector(3 downto 0);   -- SRAM A[17:14]
        SRAM_CE_N   : out   std_logic;
        SRAM_OE_N   : out   std_logic;
        SRAM_WE_N   : out   std_logic
    );
end entity C6502_Interface;

architecture Behavioral of C6502_Interface is

    -- -------------------------------------------------------------------------
    -- Address constants (offsets within the IO2 page)
    -- -------------------------------------------------------------------------
    constant C_LATCH_OFFS  : std_logic_vector(7 downto 0) := x"FD";  -- $DFFD
    constant C_PAGE_OFFS   : std_logic_vector(7 downto 0) := x"FE";  -- $DFFE
    constant C_BLOCK_OFFS  : std_logic_vector(7 downto 0) := x"FF";  -- $DFFF
    constant C_VERA_TOP    : std_logic_vector(7 downto 5) := "000";  -- $DF00-$DF1F

    -- -------------------------------------------------------------------------
    -- PHI2 two-stage synchroniser.
    -- Adds ~80 ns latency from the real PHI2 edge, well within the
    -- PHI2-high window (~490 ns at ~1 MHz).
    -- -------------------------------------------------------------------------
    signal phi2_s    : std_logic := '0';
    signal phi2_ss   : std_logic := '0';
    signal phi2_rise : std_logic;

    signal sample_cnt : integer range 0 to SAMPLE_CLKS := 0;
    signal sample     : std_logic := '0';

    -- -------------------------------------------------------------------------
    -- Internal registers
    -- -------------------------------------------------------------------------
    signal vera_sel     : std_logic := '0';                             -- VERA selected ($DFFD)
    signal georam_page  : std_logic_vector(5 downto 0) := (others => '0');
    signal georam_block : std_logic_vector(3 downto 0) := (others => '0');

    -- -------------------------------------------------------------------------
    -- Address decode (combinational)
    -- -------------------------------------------------------------------------
    signal sel_latch  : std_logic;
    signal sel_page   : std_logic;
    signal sel_block  : std_logic;
    signal sel_vera   : std_logic;
    signal sel_georam : std_logic;

begin

    -- =========================================================================
    -- Address decode
    -- =========================================================================
    sel_latch  <= '1' when IO2_N='0' and A = C_LATCH_OFFS else '0';
    sel_page   <= '1' when IO2_N='0' and A = C_PAGE_OFFS  else '0';
    sel_block  <= '1' when IO2_N='0' and A = C_BLOCK_OFFS else '0';
    sel_vera   <= '1' when IO2_N='0' and A(7 downto 5) = C_VERA_TOP and vera_sel='1' else '0';
    sel_georam <= '1' when IO1_N='0' else '0';

    -- =========================================================================
    -- PHI2 synchroniser and sample point
    -- =========================================================================
    p_sync : process (CLK)
    begin
        if rising_edge(CLK) then
            phi2_s  <= PHI2;
            phi2_ss <= phi2_s;
        end if;
    end process p_sync;

    phi2_rise <= phi2_s and not phi2_ss;

    -- sample pulses once, SAMPLE_CLKS cycles after phi2_rise, if PHI2 is
    -- still high (a short or glitched PHI2 pulse never samples).
    p_sample : process (CLK)
    begin
        if rising_edge(CLK) then
            sample <= '0';
            if phi2_rise = '1' then
                sample_cnt <= 1;
            elsif sample_cnt /= 0 then
                if phi2_ss = '0' then
                    sample_cnt <= 0;
                elsif sample_cnt = SAMPLE_CLKS then
                    sample     <= '1';
                    sample_cnt <= 0;
                else
                    sample_cnt <= sample_cnt + 1;
                end if;
            end if;
        end if;
    end process p_sample;

    -- =========================================================================
    -- Main process -- register writes in IO2
    --   1. $DFFD VERA select latch: != $00 selects, $00 deselects
    --   2. $DFFE GeoRAM page  register (6 bits)
    --   3. $DFFF GeoRAM block register (4 bits)
    -- =========================================================================
    p_main : process (CLK)
    begin
        if rising_edge(CLK) then
            if sample = '1' and RNW = '0' then

                -- 1. VERA select latch
                if sel_latch = '1' then
                    if D = x"00" then
                        vera_sel <= '0';
                    else
                        vera_sel <= '1';
                    end if;
                end if;

                -- 2. GeoRAM page register
                if sel_page = '1' then
                    georam_page <= D(5 downto 0);
                end if;

                -- 3. GeoRAM block register
                if sel_block = '1' then
                    georam_block <= D(3 downto 0);
                end if;

            end if;
        end if;
    end process p_main;

    -- =========================================================================
    -- Bus control output (combinational, gated by PHI2)
    -- =========================================================================
    VERA_CS <= '0' when sel_vera='1' and PHI2='1' else '1';

    -- =========================================================================
    -- External SRAM control (combinational, gated by PHI2)
    --
    -- Timing budget (AS6C4008-55, tAA=55 ns, C64 PHI2 high ~490 ns):
    --   /IO1 low (~50-80 ns after PHI2 rise) -> CE# low      ~0 ns  (combinational)
    --   CE# low -> data valid                                <=55 ns
    --   6510 samples read data at PHI2 fall (tDSU ~100 ns)   ample margin
    --   Write: WE# pulse = /IO1 AND PHI2 high, ~400 ns >> tWP=40 ns; data is
    --          latched by the SRAM on the WE# rising edge (PHI2 fall), when the
    --          6510 data is stable (tHW ~10 ns > tDH = 0 ns).
    --   SRAM_PAGE / SRAM_BLOCK change only on $DFFE/$DFFF writes (IO2 cycles), never
    --   while CE# is low.
    --
    -- SRAM_CE_N is also the GeoRAM term of the data transceiver (U19) output
    -- enable: the card drives the C64 bus for GeoRAM reads.
    -- =========================================================================
    SRAM_PAGE  <= georam_page;
    SRAM_BLOCK <= georam_block;

    SRAM_CE_N <= '0' when sel_georam='1' and PHI2='1'              else '1';
    SRAM_OE_N <= '0' when sel_georam='1' and PHI2='1' and RNW='1'  else '1';
    SRAM_WE_N <= '0' when sel_georam='1' and PHI2='1' and RNW='0'  else '1';

end architecture Behavioral;
