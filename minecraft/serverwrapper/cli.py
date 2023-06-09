#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import click
import click_log
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
    for package in ['click']:
        version = pkg_resources.require(package)[0].version
        print('{:40} {:}'.format(package, version))

@click.group()
def debug():
    """Debug commands
    """
    pass

@click.group()
def cli():
    """A wrapper for the Minecraft server
    """
    pass

cli.add_command(run)
cli.add_command(version)
cli.add_command(debug)

if __name__ == '__main__':
    cli()
