# NXPISP
ISP Programmer for NXP Cortex-M Chips

Command line programmer for the NXP ISP interface.

## Chip Families Supported:
    LPC84x
    LPC804

## Usage

    Erase Entire Flash: ISPProgrammer -c LPC845 masserase -d /dev/ttyUSB0
    Program Flash: ISPProgrammer -c LPC804 writeimage --imagein blinky804.hex -d /dev/ttyUSB0
    Read Chip Info: ISPProgrammer -c LPC844 querychip -d /dev/ttyUSB0

## Installation
NXPISP is a python3 package and can be installed using pip.

    1. cd NXPISP
    2. pip install .
