# isp-programmer
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
+ LPC84x
+  LPC82x
+  LPC80x

Chips using UU-encoded protocols (e.g., LPC1700 family) are not supported.
Other NXP devices with 1 kB sector sizes may work by adding their configuration to the lpctools_parts.def file.
The configuration file is identical to that used by the [lpctools project](http://git.techno-innov.fr/?p=lpctools).

## Usage
### Erase Entire Flash
```bash
isp_programmer --device /dev/ttyUSB0 -b 9600 -crystal_frequency 12000 masserase
```

### Program Flash
```bash
isp_programmer --device /dev/ttyUSB0 -b 9600 -crystal_frequency 12000 writeimage --imagein blinky804.hex
```

### Read Chip Info
```bash
isp_programmer --device /dev/ttyUSB0 -b 9600 -crystal_frequency 12000 querychip
```

## Installation
### pypi
```bash
pip install isp_programmer
```

### From Source
```bash
git clone https://github.com/snhobbs/isp-programmer.git
cd isp-programmer
pip install .
```

The default location for the configuration file is at /etc/lpctools_parts.def.
The file can either be copied there or the path passed in when calling the tool
with the --config_file/-f flag. If none is given or found then the default parts are still available.

## Similar Projects
+ https://github.com/JitterCompany/mxli
+ https://github.com/idreamoferp/nxp_isp
+ https://github.com/pzn1977/nxp_isp_loader
+ https://github.com/laneboysrc/LPC81x-ISP-tool
+ https://github.com/Senseg/lpc21isp
+ https://github.com/ulfen/nxpprog
