from setuptools import find_packages, setup

setup(
    name='minecraft-serverwrapper',
    version='0.1',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'colorama',
        'click',
        'libtmux',
        'click-log',
        'click-shell',
    ],
    entry_points='''
        [console_scripts]
        minecraft-serverwrapper=minecraft.serverwrapper.cli:cli
    ''',
)
