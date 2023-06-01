#!/usr/bin/env python
# -*- coding: utf-8 -*-

if __name__ == '__main__':
    from selftmux.controller import TmuxServerController
    #TmuxServerController('minecraft', 'src.minecraft.serverwrapper').start()
    from minecraft.serverwrapper import MinecraftServerWrapper
    MinecraftServerWrapper().start()
