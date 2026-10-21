EESchema Schematic File Version 4
EELAYER 30 0
EELAYER END
$Descr A4 11693 8268
encoding utf-8
Sheet 1 7
Title "VERA FPGA Audio & Video Board"
Date "2026-09-01"
Rev "1.0"
Comp "RetroBit Lab"
Comment1 "Gianluca Renzi"
Comment2 ""
Comment3 ""
Comment4 ""
$EndDescr
Text Notes 985  1740 0    197  ~ 39
VERA FPGA
$Sheet
S 860  865  1880 1570
U 68821B60
F0 "VeraModule" 79
F1 "vera-fpga.sch" 79
$EndSheet
$Sheet
S 4285 835  2325 1580
U 68821BC9
F0 "BusDecoder" 79
F1 "busdecoder.sch" 79
$EndSheet
Text Notes 4365 1720 0    197  ~ 39
BUS DECODER
$Sheet
S 790  3185 1960 1740
U 68821C2E
F0 "CartridgeInterface" 79
F1 "cartridgeInterface.sch" 79
$EndSheet
Text Notes 980  4255 0    177  ~ 35
CARTRIDGE\nINTERFACE
$Sheet
S 8005 830  2900 1600
U 68CF41D8
F0 "Vera FPGA flash" 79
F1 "vera-fpga-flash.sch" 79
$EndSheet
Text Notes 8130 2005 0    177  ~ 35
VERA SPI FLASH\nSD CARD INTERFACE
$Sheet
S 4700 3180 1715 1760
U 688FC286
F0 "PowerSupply" 79
F1 "powersupply.sch" 79
$EndSheet
Text Notes 4900 4270 0    197  ~ 39
POWER\nSUPPLY
$Comp
L Mechanical:Fiducial FID3
U 1 1 68BFDCEA
P 1405 6135
F 0 "FID3" H 1490 6181 50  0000 L CNN
F 1 "Fiducial" H 1490 6090 50  0000 L CNN
F 2 "Fiducial:Fiducial_0.5mm_Mask1mm" H 1405 6135 50  0001 C CNN
F 3 "~" H 1405 6135 50  0001 C CNN
	1    1405 6135
	1    0    0    -1  
$EndComp
$Comp
L Mechanical:Fiducial FID4
U 1 1 68BFDF14
P 1885 6135
F 0 "FID4" H 1970 6181 50  0000 L CNN
F 1 "Fiducial" H 1970 6090 50  0000 L CNN
F 2 "Fiducial:Fiducial_0.5mm_Mask1mm" H 1885 6135 50  0001 C CNN
F 3 "~" H 1885 6135 50  0001 C CNN
	1    1885 6135
	1    0    0    -1  
$EndComp
$Comp
L Mechanical:Fiducial FID2
U 1 1 68BFE1CD
P 2660 6140
F 0 "FID2" H 2745 6186 50  0000 L CNN
F 1 "Fiducial" H 2745 6095 50  0000 L CNN
F 2 "Fiducial:Fiducial_0.5mm_Mask1mm" H 2660 6140 50  0001 C CNN
F 3 "~" H 2660 6140 50  0001 C CNN
	1    2660 6140
	1    0    0    -1  
$EndComp
$Comp
L Mechanical:Fiducial FID1
U 1 1 68BFE3AF
P 3165 6135
F 0 "FID1" H 3250 6181 50  0000 L CNN
F 1 "Fiducial" H 3250 6090 50  0000 L CNN
F 2 "Fiducial:Fiducial_0.5mm_Mask1mm" H 3165 6135 50  0001 C CNN
F 3 "~" H 3165 6135 50  0001 C CNN
	1    3165 6135
	1    0    0    -1  
$EndComp
Wire Notes Line
	1185 5825 1185 6405
Wire Notes Line
	1185 6405 2325 6405
Wire Notes Line
	2325 6405 2325 5755
Wire Notes Line
	2325 5755 1185 5755
Wire Notes Line
	1185 5755 1185 5820
Wire Notes Line
	2515 5760 2515 6410
Wire Notes Line
	2515 6410 3610 6410
Wire Notes Line
	3610 6410 3610 5760
Wire Notes Line
	3610 5760 2515 5760
Text Notes 1280 5885 0    59   ~ 12
FIDUCIAL TOP
Text Notes 2565 5890 0    59   ~ 12
FIDUCIAL BOTTOM
$Comp
L RetroBitLab:LOGO LOGO1
U 1 1 68C1A132
P 3930 6030
F 0 "LOGO1" H 3955 6083 59  0000 L CNN
F 1 "VERA X16 LOGO" H 3955 5978 59  0000 L CNN
F 2 "RetroBitLab:x16logo" H 3930 6030 59  0001 C CNN
F 3 "" H 3930 6030 59  0001 C CNN
	1    3930 6030
	1    0    0    -1  
$EndComp
$Comp
L RetroBitLab:LOGO LOGO2
U 1 1 68C444DF
P 3930 6300
F 0 "LOGO2" H 3955 6353 59  0000 L CNN
F 1 "ATARI READY" H 3955 6248 59  0000 L CNN
F 2 "RetroBitLab:atari_ready_8mm_rev" H 3930 6300 59  0001 C CNN
F 3 "" H 3930 6300 59  0001 C CNN
	1    3930 6300
	1    0    0    -1  
$EndComp
$Comp
L RetroBitLab:LOGO LOGO3
U 1 1 68C44B75
P 4790 6025
F 0 "LOGO3" H 4815 6078 59  0000 L CNN
F 1 "KiCAD DESIGN" H 4815 5973 59  0000 L CNN
F 2 "Symbol:KiCad-Logo2_6mm_SilkScreen" H 4790 6025 59  0001 C CNN
F 3 "" H 4790 6025 59  0001 C CNN
	1    4790 6025
	1    0    0    -1  
$EndComp
$Comp
L RetroBitLab:LOGO LOGO4
U 1 1 68C454BC
P 4795 6300
F 0 "LOGO4" H 4820 6353 59  0000 L CNN
F 1 "ATARI DUO BUS" H 4820 6248 59  0000 L CNN
F 2 "RetroBitLab:DUOCart_20x11_Rev" H 4795 6300 59  0001 C CNN
F 3 "" H 4795 6300 59  0001 C CNN
	1    4795 6300
	1    0    0    -1  
$EndComp
$Comp
L RetroBitLab:LOGO LOGO5
U 1 1 68C454EE
P 5625 6020
F 0 "LOGO5" H 5650 6073 59  0000 L CNN
F 1 "ESP32_BOBOARD" H 5650 5968 59  0000 L CNN
F 2 "RetroBitLab:ESP32_BOBOARD_5V_21.7mmx21.7mm" H 5625 6020 59  0001 C CNN
F 3 "" H 5625 6020 59  0001 C CNN
	1    5625 6020
	1    0    0    -1  
$EndComp
$Comp
L RetroBitLab:Label-20mmx10mm LBL1
U 1 1 68D3F38A
P 6540 6065
F 0 "LBL1" H 6565 6065 50  0000 L CNN
F 1 "Label-20mmx10mm" H 6540 5965 50  0001 C CNN
F 2 "RetroBitLab:Label-20mmx10mm-Silkscreen" H 6540 6065 50  0001 C CNN
F 3 "" H 6540 6065 50  0001 C CNN
	1    6540 6065
	1    0    0    -1  
$EndComp
$Sheet
S 8580 3160 1720 1750
U 68F956C0
F0 "VGA Analog" 50
F1 "vga-analog.sch" 50
$EndSheet
Text Notes 8855 4190 0    197  ~ 39
VGA\nANALOG
$Comp
L Mechanical:MountingHole H1
U 1 1 68F52DE4
P 1145 6790
F 0 "H1" H 1265 6855 50  0000 L CNN
F 1 "MountingHole" H 1265 6755 50  0000 L CNN
F 2 "MountingHole:MountingHole_3.2mm_M3" H 1145 6790 50  0001 C CNN
F 3 "~" H 1145 6790 50  0001 C CNN
	1    1145 6790
	1    0    0    -1  
$EndComp
$Comp
L Mechanical:MountingHole H2
U 1 1 68FB49D3
P 1155 7025
F 0 "H2" H 1275 7090 50  0000 L CNN
F 1 "MountingHole" H 1275 6990 50  0000 L CNN
F 2 "MountingHole:MountingHole_3.2mm_M3" H 1155 7025 50  0001 C CNN
F 3 "~" H 1155 7025 50  0001 C CNN
	1    1155 7025
	1    0    0    -1  
$EndComp
$Comp
L Mechanical:MountingHole H3
U 1 1 68FB4BE9
P 1160 7220
F 0 "H3" H 1280 7285 50  0000 L CNN
F 1 "MountingHole" H 1280 7185 50  0000 L CNN
F 2 "MountingHole:MountingHole_3.2mm_M3" H 1160 7220 50  0001 C CNN
F 3 "~" H 1160 7220 50  0001 C CNN
	1    1160 7220
	1    0    0    -1  
$EndComp
$Comp
L Mechanical:MountingHole H4
U 1 1 68FB4D44
P 1170 7420
F 0 "H4" H 1290 7485 50  0000 L CNN
F 1 "MountingHole" H 1290 7385 50  0000 L CNN
F 2 "MountingHole:MountingHole_3.2mm_M3" H 1170 7420 50  0001 C CNN
F 3 "~" H 1170 7420 50  0001 C CNN
	1    1170 7420
	1    0    0    -1  
$EndComp
$EndSCHEMATC
