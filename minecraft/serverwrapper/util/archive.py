
import logging
from pathlib import Path
import os
import re
import shutil
import types
from typing import Any, Callable, Generator
import zipfile
from itertools import chain

from minecraft.serverwrapper.util.exceptions import MinecraftServerWrapperException

logger = logging.getLogger(__name__)

####################################################################################################
# Path tree traversal

exclude_patterns = ['.', '..']


class PathListFunction():
    """ Basically callable[Path, Generator[Path, None, None]] but with utils
    Can (and should) be used as a decorator.
    """
    _func: Callable[[Path], Generator[Path, None, None]] = None
    _name: str = None

    def __init__(self, fn, name=None):
        self._func = fn
        self._name = name

    def __repr__(self):
        return f'PathListFunction(name={self._name}, fn={repr(self._func)})'

    def __str__(self):
        return f'PathListFunction({self._name})'

    def __call__(self, current_path: Path) -> Generator[Path, None, None]:
        return self._func(current_path)

    def _concat(self, other):
        return PathListFunction(
            name='{} + {}'.format(self._name, other._name),
            fn=lambda current_path: chain(self._func(current_path), other._func(current_path))
        )

    def __add__(self, other):
        return self._concat(other)

    def __or__(self, other):
        return self._concat(other)


def pathLister(name: str):
    return lambda fn: PathListFunction(fn, name=name)


@pathLister('subdirectories')
def subdirectories(current_path: Path) -> Generator[Path, None, None]:
    """ Lists all subdirectories of a path
    """
    for subdirectory in current_path.iterdir():
        if subdirectory.is_dir() and subdirectory.name not in exclude_patterns:
            yield subdirectory


@pathLister('single_subdirectory')
def single_subdirectory(current_path: Path) -> Generator[Path, None, None]:
    """ Lists the only subdirectory of a path, if there is only one
    """
    dirs = [x for x in subdirectories(current_path)]
    if len(dirs) == 1:
        yield dirs[0]


def subdirectory_named(str) -> PathListFunction:
    """ Lists the subdirectories of a path with a given name
    """
    def subdirectory_named_inner(current_path: Path) -> Generator[Path, None, None]:
        for subdirectory in current_path.iterdir():
            if subdirectory.is_dir() and subdirectory.name == str:
                yield subdirectory
    return PathListFunction(subdirectory_named_inner, name='subdirectory_named({})'.format(str))


@pathLister('archives_in_dir')
def archives_in_dir(current_path: Path) -> Generator[Path, None, None]:
    for archive in list_archives(current_path):
        yield zipfile.Path(archive)


def traverse_paths(current_path: Path, traversable_children: PathListFunction, targets: PathListFunction) -> Generator[Path, None, None]:
    if not current_path.is_dir():
        raise MinecraftServerWrapperException('traverse_paths called with a non-directory path {}!'.format(current_path))
    # Targets first
    for target in targets(current_path):
        yield target
    # Then traverse children
    # OMG zipfile paths are not comparable ... why!?
    visited = set()
    for child in traversable_children(current_path):
        if child.name not in visited:
            logger.debug(f'... searching {child}')
            yield from traverse_paths(child, traversable_children, targets)
            visited.add(child.name)


####################################################################################################
# Handles archive files (zip, tar, etc.)
# TODO: For now, only zip files are supported

archive_patterns = {
    "zip": zipfile.is_zipfile
}

archive_filename_regex = re.compile(r"^(?P<name>.+)\.(?P<ext>(" + "|".join(archive_patterns.keys())  + "))$")


def _fixPathObj(path: Path or str):
    if isinstance(path, str):
        return Path(path)
    return path


def archive_pattern(filename: str or Path) -> tuple[str, str, callable]:
    match = archive_filename_regex.match(str(filename))
    if match:
        ext = match.group("ext")
        if ext in archive_patterns:
            return match.group("name"), ext, archive_patterns[ext]
    return None


def archive_type(filename: str or Path) -> str:
    pattern = archive_pattern(filename)
    if pattern:
        if pattern[2](filename):
            return pattern[1]
        else:
            logger.warning('Found file {:s} that is not a valid archive, skipping.'.format(filename))
    return None


def is_archive(filename: str or Path) -> bool:
    return archive_type(filename) is not None


def list_archives(directory: str or Path) -> Generator[Path, None, None]:
    """ Lists all the (supported) archives in a directory
    """
    directory = _fixPathObj(directory)
    for file in directory.iterdir():
        if is_archive(file):
            yield file


####################################################################################################
# TODO: Move this to a separate file


def deepsearch_for_mods_dir(directory: str or Path) -> Path or None:
    """ Searches for a mods directory in a Path and its subdirectories
    """
    dirs = traverse_paths(
        _fixPathObj(directory),
        archives_in_dir | single_subdirectory | subdirectory_named('.minecraft'),
        subdirectory_named('mods')
    )
    dirs = list(dirs)
    if len(dirs) > 1:
        logger.error('Found more than one mods directory in {:s}:'.format(directory))
        for dir in dirs:
            logger.error('  {:s}'.format(str(dir)))
        raise MinecraftServerWrapperException('Found more than one mods directory in {:s}.'.format(directory))
    elif len(dirs) == 1:
        return dirs[0]
    else:
        return None


def copy_mod_from_zip(mod_path: Path, dest_dir: Path):
    with open(dest_dir / mod_path.name, 'wb') as destf:
        with mod_path.open('rb') as srcf:
            shutil.copyfileobj(srcf, destf)
