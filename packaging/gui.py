import pathlib
import contextlib
import multiprocessing
import sys
import functools
import logging
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
from tkinter import ttk  #  noqa
import threading
import queue
import serial
import serial.tools.list_ports
import isp_programmer.cli

__version__ = "v1.2.1"

_log = logging.getLogger("isp_programmer_gui")
_min_frame_size = (200, 300)
_frame_size = (600, 800)


class StdoutQueue:
    def __init__(self, *args, **kwargs):
        self._queue = multiprocessing.Queue()

    def write(self, msg):
        self._queue.put(msg)

    def get(self):
        return self._queue.get()

    def close(self):
        self._queue.close()

    def flush(self):
        sys.__stdout__.flush()

    def get_nowait(self):
        return self._queue.get_nowait()


def list_serial_ports():
    """List available COM ports in Windows and Linux"""
    ports = serial.tools.list_ports.comports()
    return sorted([port.device for port in ports if port.description], reverse=True)


def setup_log_handler(log, output_queue, level=logging.INFO):
    handler = logging.StreamHandler(output_queue)
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)
    handler.setFormatter(formatter)
    log.setLevel(level)
    log.addHandler(handler)

    logging.getLogger("isp_programmer").addHandler(handler)
    logging.getLogger("isp_programmer").setLevel(logging.INFO)


class WorkerThread(threading.Thread):
    def __init__(self, command, output_queue, update_text):
        super().__init__()
        self.queue = output_queue
        self.command = command
        self.update_text = update_text
        self.process = None

    def kill(self):
        try:
            self.process.kill()
        except (AttributeError,):
            pass

    def is_alive(self):
        return self.process.is_alive()

    def run(self):
        # Run the command and capture stdout
        try:
            self.process = multiprocessing.Process(
                target=self.command, kwargs={"output_queue": self.queue}
            )
            self.process.start()
            while self.process.is_alive():
                try:
                    for line in self.queue.get_nowait():
                        self.update_text(line)  # Update GUI with stdout
                except queue.Empty:
                    pass

            self.process.join()
            try:
                for line in self.queue.get_nowait():
                    self.update_text(line)  # Update GUI with stdout
            except queue.Empty:
                pass

            self.update_text("\n---Task Exited---\n")

        except Exception as e:
            print(f"Error running command: {e}")
            raise e


class FilePicker(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.file_path = tk.StringVar()

        self.entry = tk.Entry(self, textvariable=self.file_path, width=50)
        self.entry.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.browse_button = tk.Button(self, text="Browse", command=self.browse_file)
        self.browse_button.grid(row=0, column=1, padx=5, pady=5)

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if file_path:
            self.file_path.set(file_path)

    def get(self):
        return self.file_path.get()


def program_isp_task(
    image, device, output_queue, baud=115200, crystal_frequency=12000, no_sync=False
):
    setup_log_handler(_log, output_queue)
    isp, chip = isp_programmer.cli.SetupChip(
        baud,
        device,
        crystal_frequency,
        isp_programmer.cli._chip_defs,
        no_sync,
    )
    bin_ = isp_programmer.cli.read_image_file_to_bin(image)
    isp_programmer.cli.WriteImage(isp, chip, bin_)
    isp.Go(0)


def erase_task(
    device, output_queue, baud=115200, crystal_frequency=12000, no_sync=False
):
    setup_log_handler(_log, output_queue)
    isp, chip = isp_programmer.cli.SetupChip(
        baud,
        device,
        crystal_frequency,
        isp_programmer.cli._chip_defs,
        no_sync,
    )
    isp_programmer.cli.MassErase(isp, chip)


class MyFrame(tk.Tk):
    def __init__(self, parent, title):
        super().__init__()
        self.worker_thread = None
        self.queue = StdoutQueue()
        self.title(title)
        self.geometry("{}x{}".format(*_frame_size))
        self.minsize(*_min_frame_size)
        self.sync_mode = tk.BooleanVar(value=True)

        version_label = tk.Label(self, text=f"Version: {__version__}")
        version_label.pack(anchor=tk.E, padx=5, pady=5)

        # File Input
        file_label = tk.Label(self, text="Select .bin File:")
        file_label.pack(anchor=tk.W, padx=5, pady=5)
        self.file_picker = FilePicker(self)
        self.file_picker.pack(anchor=tk.W, padx=5, pady=5)

        # Communication Channel selection (example: list serial ports)
        channel_label = tk.Label(self, text="Select COM Channel:")
        channel_label.pack(anchor=tk.W, padx=5, pady=5)
        com_ports = list_serial_ports()  # Fetch COM ports

        if len(com_ports) == 0:
            messagebox.showerror("Error", "No com ports found.")
            raise UserWarning("No com ports found.")

        self.com_choice = tk.StringVar(self)
        self.com_choice.set(com_ports[0])
        self.com_choice_menu = tk.ttk.Combobox(
            self, textvariable=self.com_choice, values=com_ports
        )
        self.com_choice_menu.pack(anchor=tk.W, padx=5, pady=5)

        # Sync/No Sync Checkbutton
        sync_label = tk.Label(self, text="Enable Sync:")
        sync_label.pack(anchor=tk.W, padx=5, pady=5)

        self.sync_checkbutton = tk.Checkbutton(
            self,
            text="Sync",
            variable=self.sync_mode,
            onvalue=True,  # Sync mode
            offvalue=False,  # No Sync mode
            # command=self.update_sync_mode,
        )
        self.sync_checkbutton.pack(anchor=tk.W, padx=5, pady=5)

        # program isp button
        self.run_isp_button = tk.Button(
            self, text="Program", command=self.on_run_program_isp
        )
        self.run_isp_button.pack(pady=10)

        # erase isp button
        self.run_erase_button = tk.Button(self, text="Erase", command=self.on_run_erase)
        self.run_erase_button.pack(pady=10)

        # Cancel Button
        self.run_button = tk.Button(self, text="Cancel", command=self.on_cancel)
        self.run_button.pack(pady=10)

        # self.state_label = tk.Label(self, text="Current State: Initialized")
        # self.state_label.pack(anchor=tk.W, padx=5, pady=5)

        # Terminal Output
        terminal_label = tk.Label(self, text="Terminal Output:")
        terminal_label.pack(anchor=tk.W, padx=5, pady=5)
        self.terminal_output = scrolledtext.ScrolledText(
            self, wrap=tk.WORD, state=tk.DISABLED
        )
        self.terminal_output.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.worker_thread = None
        # self.Show()

    def get_validation_errors(self):
        errors = []
        com_ports = list_serial_ports()
        if self.com_choice.get() not in com_ports:
            errors.append("No com port selected")

        return errors

    def update_text(self, line):
        # Use after() to update the text area in the main GUI thread
        self.after(0, lambda: self.terminal_output.insert(tk.END, line))
        self.after(0, lambda: self.terminal_output.see(tk.END))  # Scroll to the bottom

    def on_cancel(self):
        if self.worker_thread is not None and self.worker_thread.is_alive():
            self.worker_thread.kill()

    def on_run_erase(self):
        """Function of a never-ending program writing to terminal"""
        if self.worker_thread is not None and self.worker_thread.is_alive():
            messagebox.showerror("Error", "Thread Already Running")
            return

        errors = self.get_validation_errors()

        if len(errors):
            messagebox.showerror("Validation Error", "\n".join(errors))
            return

        com_choice = self.com_choice.get()
        self.update_text(f"Starting task. Device {com_choice}\n")
        command = functools.partial(
            erase_task,
            device=com_choice,
            no_sync=(not self.sync_mode.get()),
        )

        self.terminal_output.configure(state=tk.NORMAL)
        self.terminal_output.insert(
            tk.END, "Starting Task, please wait...\nExpected to update in 45 seconds\n"
        )
        self.worker_thread = WorkerThread(command, self.queue, self.update_text)
        self.worker_thread.start()

    def on_run_program_isp(self):
        """Function of a never-ending program writing to terminal"""
        if self.worker_thread is not None and self.worker_thread.is_alive():
            messagebox.showerror("Error", "Thread Already Running")
            return

        errors = self.get_validation_errors()

        bin_file = self.file_picker.get()
        if not bin_file or not pathlib.Path(bin_file).exists():
            errors.append("No binary selected or file not found")

        if len(errors):
            messagebox.showerror("Validation Error", "\n".join(errors))
            return

        com_choice = self.com_choice.get()

        bin_file = self.file_picker.get()
        self.update_text(f"Starting task. Device {com_choice}, Bin {bin_file}\n")
        command = functools.partial(
            program_isp_task,
            image=bin_file,
            device=com_choice,
            no_sync=(not self.sync_mode.get()),
        )

        msg = f"programming {bin_file}, {com_choice}"
        _log.debug(msg)

        self.terminal_output.configure(state=tk.NORMAL)
        self.terminal_output.insert(
            tk.END, "Starting Task, please wait...\nExpected to update in 45 seconds\n"
        )
        # self.terminal_output.configure(state=tk.DISABLED)
        # self.state_label.config(text="Current State: Running")
        self.worker_thread = WorkerThread(command, self.queue, self.update_text)
        self.worker_thread.start()
        # self.state_label.config(text="Current State: Ready")

    def on_close(self):
        """Clean up thread on frame close"""
        if hasattr(self, "process_thread") and self.process_thread.is_alive():
            self.process_thread.join()
        with contextlib.suppress(AttributeError):
            self.worker_thread.kill()
            self.worker_thread.join(1)
        self.destroy()


def main():
    multiprocessing.freeze_support()  # required for windows support so we don't get multiple windows opening
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetDllDirectoryW(None)

    app = MyFrame(None, title="NXP ISP Programmer")
    app.protocol("WM_DELETE_WINDOW", app.on_close)

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(format=log_format)
    logging.getLogger("isp_programmer").setLevel(logging.DEBUG)
    _log.setLevel(logging.INFO)
    app.mainloop()


if __name__ == "__main__":
    main()
