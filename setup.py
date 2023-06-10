from setuptools import find_packages, setup

setup(
    name='minecraft-serverwrapper',
    version='0.4.1',
    packages=find_packages(),
    package_data={'minecraft.serverwrapper': ['*.yaml']},
    include_package_data=True,
    install_requires=[
        'pyyaml',
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
