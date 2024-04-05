import os
import logging
import click
from .ISPConnection import UartDevice, BAUDRATES, ISPConnection, SetupChip, MassErase, read_image_file_to_bin, ReadImage, WriteBinaryToFlash, WriteImage


_chip_defs = os.path.join(os.path.dirname(__file__), "lpctools_parts.def")

@click.group()
@click.option('--device', '-d', default='/dev/ttyUSB0', help='Serial device')
@click.option('--baud', '-b', type=int, default=BAUDRATES[0], help='Baudrate')
@click.option('--crystal-frequency', '-c', type=int, default=12000,
              help="Crystal frequency of chip in khz")
@click.option('--config-file', '-f', default=_chip_defs,
              help='Parts definition file')
@click.option('--echo', is_flag=True)
@click.option('--no-sync', is_flag=True)
@click.option('--sleep-time', '-s', type=float, default=0.25, help='Sleep time between commands')
@click.option('--serial-sleep', type=float, default=0, help='Sleep time between serial bytes')
@click.option('--debug', is_flag=True)
@click.pass_context
def gr1(ctx, **kwargs):
    ctx.ensure_object(dict)
    ctx.obj.update(kwargs)
    logging.basicConfig()

    if kwargs["debug"]:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)


@gr1.command("sync", help="Read the chip ID and boot code")
@click.pass_context
def cli_sync(ctx):
    iodevice = UartDevice(ctx.obj['device'], baudrate=ctx.obj['baud'])
    isp = ISPConnection(iodevice)
    isp.SyncConnection()


@gr1.command("query-chip", help="Read the chip ID and boot code")
@click.pass_context
def cli_QueryChip(ctx):
    iodevice = UartDevice(ctx.obj['device'], baudrate=ctx.obj['baud'])
    isp = ISPConnection(iodevice)
    boot_version = isp.ReadBootCodeVersion()
    uid = isp.ReadUID()
    part_id = isp.ReadPartID()
    logging.info("Part ID: 0x%x\tPart UID: %s\tBoot Code Version: %s", part_id, uid, boot_version)


@gr1.command("erase", help="Erase entire chip")
@click.pass_context
def cli_MassErase(ctx):
    isp, chip = SetupChip(ctx.obj['baud'], ctx.obj['device'], ctx.obj['crystal_frequency'], ctx.obj['config_file'], ctx.obj['no_sync'], ctx.obj['sleep_time'], serial_sleep=ctx.obj['serial_sleep'])
    MassErase(isp, chip)
    logging.info("Mass Erase Successful")


@click.option('--start_sector', type=int, default=0, required=True, help='Sector to write to')
@click.option('--imagein', type=str, required=True, help='Location of hex file to program')
@gr1.command("write-flash", help="Write a specific flash sector")
@click.pass_context
def cli_WriteFlash(ctx, imagein, start_sector):
    isp, chip = SetupChip(ctx.obj['baud'], ctx.obj['device'], ctx.obj['crystal_frequency'], ctx.obj['config_file'], ctx.obj['no_sync'], ctx.obj['sleep_time'], serial_sleep=ctx.obj['serial_sleep'])
    image = read_image_file_to_bin(imagein)
    WriteBinaryToFlash(isp=isp, chip=chip, image=image, start_sector=start_sector)


@click.option('--imagein', type=str, required=True, help='Location of hex file to program')
@gr1.command("write-image", help="Write image")
@click.pass_context
def cli_WriteImage(ctx, imagein):
    isp, chip = SetupChip(ctx.obj['baud'], ctx.obj['device'], ctx.obj['crystal_frequency'], ctx.obj['config_file'], ctx.obj['no_sync'], ctx.obj['sleep_time'], serial_sleep=ctx.obj['serial_sleep'])
    image = read_image_file_to_bin(imagein)
    WriteImage(isp, chip, image)
    isp.Go(0)


@click.option('--imagein', type=str, required=True, help='Location of hex file to program')
@gr1.command("fast-write-image", help='Test CRC and exit if it matches the flash')
@click.pass_context
def cli_FastWriteImage(ctx, imagein):
    isp, chip = SetupChip(ctx.obj['baud'], ctx.obj['device'], ctx.obj['crystal_frequency'], ctx.obj['config_file'], ctx.obj['no_sync'], ctx.obj['sleep_time'], serial_sleep=ctx.obj['serial_sleep'])
    image = read_image_file_to_bin(imagein)
    image_read = ReadImage(isp, chip)[:len(image)]
    if bytes(image) == image_read:
        logging.getLogger().info("Already programmed")
    else:
        WriteImage(isp, chip, image, flash_write_sleep=0)
        isp.Go(0)


@click.option('--imageout', type=str, required=True, help='Name of hex file output')
@gr1.command("read-image", help="Read the chip image")
@click.pass_context
def cli_ReadImage(ctx, imageout: str):
    isp, chip = SetupChip(ctx.obj['baud'], ctx.obj['device'], ctx.obj['crystal_frequency'], ctx.obj['config_file'], ctx.obj['no_sync'], ctx.obj['sleep_time'], serial_sleep=ctx.obj['serial_sleep'])
    image = ReadImage(isp, chip)
    logging.getLogger().debug(image)
    with open(imageout, 'wb') as f:
        f.write(image)


def main():
    gr1()


if __name__ == "__main__":
    main()
