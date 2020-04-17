# NXPISP
ISP Programmer for NXP Cortex-M Chips

Command line programmer for the NXP ISP interface.

## Features
### Secure Write
The checksum in flash is written to zero as the first write, so if the upload
fails the chip will boot back into the ISP mode.
The image is then written from the top most page down to the first page.
The first sector contains the valid image checksum so a failed write will
keep the device in ISP mode instead of just being bricked.
  
## Chip Families Supported:
    LPC84x
    LPC80x

NXP chips with 1kB sector sizes should work by adding their information to the
lpctools_parts.def configuration file.

The configuration file is identical to that used by the lpctools project 
<http://git.techno-innov.fr/?p=lpctools>

## Usage

    Erase Entire Flash: ISPProgrammer --device /dev/ttyUSB0 -b 9600 -crystal_frequency 12000 masserase
    Program Flash: ISPProgrammer --device /dev/ttyUSB0 -b 9600 -crystal_frequency 12000 writeimage --imagein blinky804.hex
    Read Chip Info: ISPProgrammer --device /dev/ttyUSB0 -b 9600 -crystal_frequency 12000 querychip

## Installation
NXPISP is a python3 package and can be installed using pip.
Clone the repository, enter the directory with setup.py in it and run
pip install .
The default location for the configuration file is at /etc/lpctools_parts.def. 
The file can either be copied there or the path passed in when calling the tool
with the --config_file/-f flag.

    1. cd NXPISP
    2. pip install .
    3. cp lpctools_parts.def /etc
