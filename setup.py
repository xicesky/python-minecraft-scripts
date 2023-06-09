from setuptools import find_packages, setup

setup(
    name='minecraft-serverwrapper',
    version='0.3.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'colorama',
        'click',
        'click-log',
        'click-shell',
    ],
    entry_points='''
        [console_scripts]
        minecraft-serverwrapper=minecraft.serverwrapper.cli:cli
    ''',
)
