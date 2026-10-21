#!/bin/bash

# Remove all unwanted files
rm $1.aux 2>/dev/null
rm $1.log 2>/dev/null
rm $1.toc 2>/dev/null
rm $1.out 2>/dev/null

pdflatex -interaction=nonstopmode $1.tex 1>/dev/null 2>/dev/null
RES=$?
if [ ${RES} -eq 0 ]; then
	pdflatex -interaction=nonstopmode $1.tex 1>/dev/null 2>/dev/null
	RES=$?
else
	echo "Error."
fi

# Remove all unwanted files
rm $1.aux 2>/dev/null
rm $1.log 2>/dev/null
rm $1.toc 2>/dev/null
rm $1.out 2>/dev/null

exit $RES
