
# click log is not working as i like it to work

import logging
import click


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
