#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import click
import click_log

# Set up logging
root_logger = logging.getLogger()
click_log.basic_config(root_logger)
root_logger.setLevel(logging.INFO)
#root_logger.handlers[0].formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(funcName)s:%(lineno)d - %(message)s")
root_logger.handlers[0].formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

class NotYetImplementedError(click.ClickException):
    """Exception raised when a command is not yet implemented
    """
    
    exit_code = 10
    
    def __init__(self, message):
        super().__init__(message)

@click.command()
def start():
    """Starts or attaches to the server in a tmux session
    """
    from selftmux.controller import TmuxServerController
    TmuxServerController('minecraft', 'src.minecraft.serverwrapper').start()

@click.command()
@click_log.simple_verbosity_option(logger)
def stop():
    """Stops the server
    """
    #click.echo("Sorry, this command is not implemented yet")
    logger.debug("Sorry, this command is not implemented yet")
    logger.info("Sorry, this command is not implemented yet")
    logger.error("Sorry, this command is not implemented yet")
    raise NotYetImplementedError("Sorry, this command is not implemented yet")
    # from selftmux.controller import TmuxServerController
    # TmuxServerController('minecraft', 'src.minecraft.serverwrapper').stop()
    return 1

@click.command()
@click_log.simple_verbosity_option(logger)
def run():
    """Runs the server in the foreground
    """
    from minecraft.serverwrapper import MinecraftServerWrapper
    MinecraftServerWrapper().start()

@click.group()
def cli():
    """A wrapper for the Minecraft server
    """
    pass

cli.add_command(start)
cli.add_command(stop)
cli.add_command(run)

if __name__ == '__main__':
    cli()
