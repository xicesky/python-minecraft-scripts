#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import click
import click_log
from minecraft.serverwrapper.selftmux.controller import TmuxServerController
from minecraft.serverwrapper.serverwrapper import MinecraftServerWrapper
from minecraft.serverwrapper.util.logging import setup_root_logger

# Set up logging
root_logger = setup_root_logger()
logger = logging.getLogger(__name__)

class NotYetImplementedError(click.ClickException):
    """Exception raised when a command is not yet implemented
    """
    exit_code = 10
    
    def __init__(self, message):
        super().__init__(message)

@click.command()
@click_log.simple_verbosity_option(root_logger)
def start():
    """Starts or attaches to the server in a tmux session
    """
    TmuxServerController('minecraft', 'minecraft.serverwrapper.cli', ['run']).start()

@click.command()
@click_log.simple_verbosity_option(root_logger)
def stop():
    """Stops the server
    """
    #click.echo("Sorry, this command is not implemented yet")
    logger.debug("Sorry, this command is not implemented yet")
    logger.info("Sorry, this command is not implemented yet")
    logger.error("Sorry, this command is not implemented yet")
    raise NotYetImplementedError("Sorry, this command is not implemented yet")
    # from selftmux.controller import TmuxServerController
    # TmuxServerController('minecraft', 'minecraft.serverwrapper.cli').stop()
    return 1

@click.command()
@click_log.simple_verbosity_option(root_logger)
def run():
    """Runs the server in the foreground
    """
    MinecraftServerWrapper().start()
    
@click.command()
@click_log.simple_verbosity_option(root_logger)
def version():
    """Prints the version of this script and included libraries
    """
    # TODO: Add git hash at "build time" and print it here
    import pkg_resources  # part of setuptools
    # TODO: Automatically get the package names from the Pipfile
    package='minecraft-serverwrapper'
    version = pkg_resources.require(package)[0].version
    print('{:40} {:}'.format(package, version))    
    for package in ['click', 'libtmux']:
        version = pkg_resources.require(package)[0].version
        print('{:40} {:}'.format(package, version))

@click.group()
def debug():
    """Debug commands
    """
    pass

@click.command()
@click_log.simple_verbosity_option(root_logger, default='DEBUG')
def tmux_sessions():
    """Debugs the tmux sessions
    """
    # logger.warning('Root logger level is: ' + str(root_logger.level))
    TmuxServerController('minecraft', 'minecraft.serverwrapper.cli').debug_tmux_sessions()

debug.add_command(tmux_sessions)

@click.group()
def cli():
    """A wrapper for the Minecraft server
    """
    pass

cli.add_command(start)
cli.add_command(stop)
cli.add_command(run)
cli.add_command(version)
cli.add_command(debug)

if __name__ == '__main__':
    cli()
