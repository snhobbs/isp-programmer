import os
import logging
import click
from .ISPConnection import (
    UartDevice,
    BAUDRATES,
    ISPConnection,
    SetupChip,
    MassErase,
    read_image_file_to_bin,
    ReadImage,
    WriteBinaryToFlash,
    WriteImage,
)


_log = logging.getLogger("isp_programmer")

_chip_defs = os.path.join(os.path.dirname(__file__), "lpctools_parts.def")


@click.group()
@click.option("--device", "-d", default="/dev/ttyUSB0", help="Serial device")
@click.option("--baud", "-b", type=int, default=BAUDRATES[0], help="Baudrate")
@click.option(
    "--crystal-frequency",
    "-c",
    type=int,
    default=12000,
    help="Crystal frequency of chip in khz",
)
@click.option("--config-file", "-f", default=_chip_defs, help="Parts definition file")
@click.option("--echo", is_flag=True)
@click.option("--no-sync", is_flag=True)
@click.option(
    "--sleep-time", "-s", type=float, default=0.25, help="Sleep time between commands"
)
@click.option(
    "--serial-sleep", type=float, default=0, help="Sleep time between serial bytes"
)
@click.option("--debug", is_flag=True)
@click.pass_context
def gr1(ctx, **kwargs):
    ctx.ensure_object(dict)
    ctx.obj.update(kwargs)

    logging.basicConfig()
    level = logging.INFO
    if kwargs["debug"]:
        level = logging.DEBUG

    _log.setLevel(level)


@gr1.command("sync", help="Synchronize connection to chip")
@click.pass_context
def cli_sync(ctx):
    iodevice = UartDevice(ctx.obj["device"], baudrate=ctx.obj["baud"])
    isp = ISPConnection(iodevice)
    isp.SyncConnection()


@gr1.command("query-chip", help="Read chip Part ID, UID, and boot code version")
@click.pass_context
def cli_QueryChip(ctx):
    iodevice = UartDevice(ctx.obj["device"], baudrate=ctx.obj["baud"])
    isp = ISPConnection(iodevice)
    boot_version = isp.ReadBootCodeVersion()
    uid = isp.ReadUID()
    part_id = isp.ReadPartID()
    _log.info(
        "Part ID: 0x%x\tPart UID: %s\tBoot Code Version: %s", part_id, uid, boot_version
    )


@gr1.command("erase", help="Erase entire chip")
@click.pass_context
def cli_MassErase(ctx):
    isp, chip = SetupChip(
        ctx.obj["baud"],
        ctx.obj["device"],
        ctx.obj["crystal_frequency"],
        ctx.obj["config_file"],
        ctx.obj["no_sync"],
    )
    MassErase(isp, chip)
    _log.info("Mass Erase Successful")


@click.option("--start_sector", type=int, default=0, help="Sector to write to")
@click.option(
    "--imagein", type=str, required=True, help="Location of hex file to program"
)
@gr1.command("write-flash", help="Write a specific flash sector")
@click.pass_context
def cli_WriteFlash(ctx, imagein, start_sector):
    isp, chip = SetupChip(
        ctx.obj["baud"],
        ctx.obj["device"],
        ctx.obj["crystal_frequency"],
        ctx.obj["config_file"],
        ctx.obj["no_sync"],
    )
    image = read_image_file_to_bin(imagein)
    WriteBinaryToFlash(isp=isp, chip=chip, image=image, start_sector=start_sector)


@click.option(
    "--imagein", type=str, required=True, help="Location of hex file to program"
)
@gr1.command("write-image", help="Write image")
@click.pass_context
def cli_WriteImage(ctx, imagein):
    isp, chip = SetupChip(
        ctx.obj["baud"],
        ctx.obj["device"],
        ctx.obj["crystal_frequency"],
        ctx.obj["config_file"],
        ctx.obj["no_sync"],
    )
    image = read_image_file_to_bin(imagein)
    WriteImage(isp, chip, image)
    isp.Go(0)


@click.option(
    "--imagein", type=str, required=True, help="Location of hex file to program"
)
@gr1.command("fast-write-image", help="Test CRC and exit if it matches the flash")
@click.pass_context
def cli_FastWriteImage(ctx, imagein):
    isp, chip = SetupChip(
        ctx.obj["baud"],
        ctx.obj["device"],
        ctx.obj["crystal_frequency"],
        ctx.obj["config_file"],
        ctx.obj["no_sync"],
    )
    image = read_image_file_to_bin(imagein)
    image_read = ReadImage(isp, chip)[: len(image)]
    if bytes(image) == image_read:
        _log.info("Already programmed")
    else:
        WriteImage(isp, chip, image, flash_write_sleep=0)
        isp.Go(0)


@click.option("--imageout", type=str, required=True, help="Name of hex file output")
@gr1.command("read-image", help="Read the chip image")
@click.pass_context
def cli_ReadImage(ctx, imageout: str):
    isp, chip = SetupChip(
        ctx.obj["baud"],
        ctx.obj["device"],
        ctx.obj["crystal_frequency"],
        ctx.obj["config_file"],
        ctx.obj["no_sync"],
    )
    image = ReadImage(isp, chip)
    _log.debug(image)
    with open(imageout, "wb") as f:
        f.write(image)


def main():
    gr1()


if __name__ == "__main__":
    main()
