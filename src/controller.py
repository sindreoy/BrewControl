#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "Sindre Bakke Oeyen"
__copyright__ = "None"
__credits__ = ["Sindre Bakke Oeyen"]
__license__ = "None"
__version__ = "1.0.0"
__maintainer__ = "Sindre Bakke Oeyen"
__email__ = "sindre.bakke.oyen@gmail.com"
__status__ = "Production"


class Controller:
    def __init__(self, y):
        self.y = y

    class Meta:
        abstract = True


class PIController(Controller):
    def __init__(self, y):
        super(PIController, self).__init__()


class LQRController(Controller):
    pass


class MPCController(Controller):
    pass
