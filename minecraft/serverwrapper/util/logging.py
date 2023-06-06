
# click log is not working as i like it to work

import logging
import click
import click_log

class MyColorFormatter(logging.Formatter):
    colors = {
        'error': dict(fg='red'),
        'exception': dict(fg='red'),
        'critical': dict(fg='red'),
        'debug': dict(fg='blue'),
        'warning': dict(fg='yellow')
    }
    # delegate = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(funcName)s:%(lineno)d - %(message)s")
    # delegate = logging.Formatter(fmt="%(asctime)s %(levelname)s %(message)s", style='%')
    # delegate = logging.Formatter(style='{', fmt="{asctime} {levelname:10} {name:30} {message}")
    delegate = logging.Formatter(style='{', fmt="{asctime} {levelname:10} {message}")
    
    def __init__(self, delegate=None):
        if delegate is not None:
            self.delegate = delegate

    def format(self, record):
        if not record.exc_info:
            level = record.levelname.lower()
            msg = self.delegate.format(record)
            if level in self.colors:
                return click.style(msg, **self.colors[level])
            return msg
        return self.delegate.format(self, record)


def setup_root_logger():
    # Set up logging
    root_logger = logging.getLogger()
    click_log.basic_config(root_logger)
    root_logger.setLevel(logging.INFO)
    root_logger.handlers[0].formatter = MyColorFormatter()
    # Also reduce logging of a few other modules
    logging.getLogger('libtmux.common').setLevel(logging.INFO)
    return root_logger
