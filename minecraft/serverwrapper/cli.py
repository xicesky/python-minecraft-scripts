#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import click
import click_log
import pkg_resources  # part of setuptools
from minecraft.serverwrapper.config import get_default_config_string
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


def format_version(package):
    version = pkg_resources.require(package)[0].version
    return '{:40} {:}'.format(package, version)

@click.command()
@click_log.simple_verbosity_option(root_logger)
def version():
    """Prints the version of this script and included libraries
    """
    # TODO: Add git hash at "build time" and print it here
    # TODO: Automatically get the package names from the Pipfile
    print(format_version('minecraft-serverwrapper'))
    print('')
    print('Used libraries:')
    for package in ['pyyaml', 'colorama', 'click']:
        print(format_version(package))

@click.command(name='show-default')
def show_default_config():
    """Prints the default configuration
    """
    print(get_default_config_string())

@click.command(name='show')
def show_current_config():
    """Prints the current configuration
    """
    print(MinecraftServerWrapper()._config.to_yaml())

@click.group()
def config():
    """Commands for managing the configuration
    """
    pass


config.add_command(show_default_config)
config.add_command(show_current_config)

@click.command(name='sync')
def sync_modpack():
    """Synchronizes provided modpack with the server
    """
    MinecraftServerWrapper().sync_modpack()


@click.group()
def modpack():
    """Commands for managing the modpack
    """
    pass


modpack.add_command(sync_modpack)


@click.group()
def cli():
    """A wrapper for the Minecraft server
    """
    pass


cli.add_command(config)
cli.add_command(modpack)
cli.add_command(run)
cli.add_command(version)

if __name__ == '__main__':
    cli()
