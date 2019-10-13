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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, pyqtSlot

import RPi.GPIO as GPIO
import threading
import numpy as np
import pyqtgraph as pg
import os
import time

from w1thermsensor import W1ThermSensor

sensor = W1ThermSensor()

"""
# EDIT BETWEEN HERE
        self.history_graphics = pg.PlotWidget(self.history_frame)
        # AND HERE
"""

# Global, constant variables
CONTROL_OPTIONS = ["PI", "LQR", "MPC"]
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
UPDATE_PLOT_TIME_CONSTANT = 3  # Three seconds intervals
UPDATE_CONTROL_TIME_CONSTANT = 3  # Three seconds intervals
THORIZON = 30  # Plot 30 seconds back in time

# Plot options
pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")
pg.setConfigOptions(antialias=True)
BLACK_PEN = pg.mkPen("k", width=3)
RED_PEN = pg.mkPen("r", width=3, style=QtCore.Qt.DashLine)

# RPi options for pins
# GPIO.setmode(GPIO.BCM)
# GPIO.setwarnings(False)
# GPIO.setup(2, GPIO.OUT)


class Ui_MainWindow(QtWidgets.QMainWindow):  # Edited inherited
    # Signal to indicate new data acquisition
    # Note: signals need to be defined inside a QObject class/subclass
    data_acquired = pyqtSignal(np.ndarray)

    def __init__(self):
        super(Ui_MainWindow, self).__init__()
        self.setupUi(self)

        # Set pump option to off
        self.radio_pump_off.setChecked(True)

        # Add control options
        self.control_technique_dropdown.addItems(CONTROL_OPTIONS)

        # Connect event listeners
        self.radio_pump_off.clicked.connect(self.pump_off)
        self.radio_pump_on.clicked.connect(self.pump_on)
        self.temperature_setpoint_btn.clicked.connect(
            self.change_temperature_setpoint
        )
        self.start_control_btn.clicked.connect(self.start_control)
        self.stop_control_btn.clicked.connect(self.stop_control)

        # Add beer icon
        self.setWindowIcon(
            QtGui.QIcon(SCRIPT_DIR + os.path.sep + "icons/beer-icon.jpg")
        )

        # Add pens to plots
        self.history_graphics.setRange(xRange=[-THORIZON, 0])
        self.curveTs = self.history_graphics.plot(pen=RED_PEN)
        self.curveT = self.history_graphics.plot(pen=BLACK_PEN)

        # Set pointer to count elements in temperature arrays
        self.ptr = 0

        # Set initial time
        self.t0 = time.time()

        # Set default temperature setpoint
        self.temperature_setpoint_spinbox.setValue(67.00)
        self.change_temperature_setpoint()

        # Initialise time and temperature arrays
        self.time_arr = np.zeros(100)
        self.Ts_arr = np.zeros(100)
        self.T_arr = np.zeros(100)

        # Connect the signal
        self.data_acquired.connect(self.update)

        # Event that kills plotting thread
        self.plot_threadkill = threading.Event()
        # Thread that starts plotting
        self.plot_thread = threading.Thread(
            name="plotting_thread",
            target=self.generate_data,
            args=(self.data_acquired.emit, self.plot_threadkill),
        )
        self.plot_thread.start()

        # Event that kills controller thread
        self.control_threadkill = threading.Event()
        # Thread that starts control loop
        self.controller_thread = threading.Thread(
            name="control_worker",
            target=self.control_temperature,
            args=(self.control_threadkill,),
        )

    # Kill our data acquisition thread when shutting down
    def closeEvent(self, close_event):
        print("PyQt5 application terminating!")
        self.plot_threadkill.set()
        print("Plotting thread killed")
        if self.controller_thread.is_alive():
            self.control_threadkill.set()
            print("Controller thread killed")
        else:
            print("Controller thread already dead")

    def generate_data(self, callback, plot_threadkill):
        while not plot_threadkill.is_set():
            self.time_arr[self.ptr] = time.time() - self.t0
            self.Ts_arr[self.ptr] = self.temperature_setpoint_lcd.value()

            # Update measurements
            # Use this line for testing outside production environment
            # self.T_arr[self.ptr] = np.cos(self.time_arr[self.ptr])
            T_meas = sensor.get_temperature()
            self.temperature_measurement_lcd.display(f"{T_meas:3.2f}")
            self.T_arr[self.ptr] = T_meas
            # Update pointer denoting how many measurements we have
            self.ptr += 1
            if self.ptr >= self.Ts_arr.shape[0]:
                # If array has values in all its indices, double its size
                # TODO: Add a doubling of size of measurement array
                tmp_Ts = self.Ts_arr
                tmp_T = self.T_arr
                tmp_t = self.time_arr
                self.Ts_arr = np.zeros(self.Ts_arr.shape[0] * 2)
                self.T_arr = np.zeros(self.T_arr.shape[0] * 2)
                self.time_arr = np.zeros(self.time_arr.shape[0] * 2)
                self.Ts_arr[: tmp_Ts.shape[0]] = tmp_Ts
                self.T_arr[: tmp_T.shape[0]] = tmp_T
                self.time_arr[: tmp_t.shape[0]] = tmp_t
            t = self.time_arr
            T_set = self.Ts_arr
            T_meas = self.T_arr
            data = np.stack([t, T_set, T_meas], axis=0)
            callback(data)
            time.sleep(UPDATE_PLOT_TIME_CONSTANT)

    # Slot to receive acquired data and update plot
    @pyqtSlot(np.ndarray)
    def update(self, data):
        xs_to_plot = self.time_arr - self.time_arr[self.ptr - 1]
        indices = np.where(xs_to_plot[: self.ptr] > -THORIZON)
        xs_to_plot = xs_to_plot[indices]
        ys_to_plot = self.Ts_arr[indices]
        ymeas_to_plot = self.T_arr[indices]
        if ys_to_plot.size > 1:
            Ts = self.Ts_arr
            T = self.T_arr
            ymin = 0.9 * np.min(np.minimum(Ts, T))
            ymax = 1.1 * np.max(np.maximum(Ts, T))
            self.history_graphics.setRange(
                xRange=[-THORIZON, 0], yRange=[ymin, ymax], update=True
            )
            self.curveTs.setData(
                xs_to_plot,
                ys_to_plot[:-1],
                stepMode=True,
                parent=self.history_graphics,
            )
            self.curveT.setData(
                xs_to_plot, ymeas_to_plot, parent=self.history_graphics
            )

    def pump_off(self):
        GPIO.output(2, GPIO.LOW)
        print("Pump is off")

    def pump_on(self):
        GPIO.output(2, GPIO.HIGH)
        print("Pump is on")

    def change_temperature_setpoint(self):
        print("Changing temperature setpoint")
        value = self.temperature_setpoint_spinbox.value()
        self.temperature_setpoint_lcd.display(value)
        print(self.temperature_setpoint_lcd.value())
        self.temperature_setpoint_lcd.repaint()

    def start_control(self):
        control_option = self.control_technique_dropdown.currentText()
        print(f"Starter regulering med {control_option}")

        # If event has been set, reset the variable
        if self.control_threadkill.is_set():
            self.stop_event = threading.Event()

        # If threads are not started, start them
        if not self.controller_thread.is_alive():
            self.controller_thread = threading.Thread(
                name="control_worker",
                target=self.control_temperature,
                args=(self.control_threadkill,),
            )
            self.controller_thread.start()

    def control_temperature(self, control_threadkill):
        while not control_threadkill.is_set():
            print("Regulerer!!!")
            time.sleep(UPDATE_CONTROL_TIME_CONSTANT)

    def stop_control(self):
        button_reply = QtWidgets.QMessageBox.question(
            self,
            "Obs!",
            "Vil du virkelig stoppe reguleringen?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if button_reply == QtWidgets.QMessageBox.Yes:
            try:
                self.control_threadkill.set()
            except AttributeError:
                pass
            finally:
                print("Stopper regulering!")
        else:
            print("Regulering fortsetter")

    # Auto-generated starts here
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(577, 544)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.gridLayout_7 = QtWidgets.QGridLayout(self.centralwidget)
        self.gridLayout_7.setObjectName("gridLayout_7")
        self.pump_frame = QtWidgets.QFrame(self.centralwidget)
        self.pump_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.pump_frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.pump_frame.setObjectName("pump_frame")
        self.gridLayout_6 = QtWidgets.QGridLayout(self.pump_frame)
        self.gridLayout_6.setObjectName("gridLayout_6")
        self.radio_pump_on = QtWidgets.QRadioButton(self.pump_frame)
        self.radio_pump_on.setObjectName("radio_pump_on")
        self.gridLayout_6.addWidget(self.radio_pump_on, 1, 0, 1, 1)
        self.pump_label = QtWidgets.QLabel(self.pump_frame)
        self.pump_label.setObjectName("pump_label")
        self.gridLayout_6.addWidget(self.pump_label, 0, 0, 1, 1)
        self.radio_pump_off = QtWidgets.QRadioButton(self.pump_frame)
        self.radio_pump_off.setObjectName("radio_pump_off")
        self.gridLayout_6.addWidget(self.radio_pump_off, 1, 3, 1, 1)
        self.gridLayout_7.addWidget(self.pump_frame, 1, 0, 1, 1)
        self.control_technique_frame = QtWidgets.QFrame(self.centralwidget)
        self.control_technique_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.control_technique_frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.control_technique_frame.setObjectName("control_technique_frame")
        self.gridLayout_4 = QtWidgets.QGridLayout(self.control_technique_frame)
        self.gridLayout_4.setObjectName("gridLayout_4")
        self.control_technique_label = QtWidgets.QLabel(
            self.control_technique_frame
        )
        self.control_technique_label.setObjectName("control_technique_label")
        self.gridLayout_4.addWidget(self.control_technique_label, 0, 0, 1, 1)
        self.control_technique_dropdown = QtWidgets.QComboBox(
            self.control_technique_frame
        )
        self.control_technique_dropdown.setEditable(False)
        self.control_technique_dropdown.setObjectName(
            "control_technique_dropdown"
        )
        self.gridLayout_4.addWidget(self.control_technique_dropdown, 0, 1, 1, 1)
        self.gridLayout_7.addWidget(self.control_technique_frame, 1, 1, 1, 1)
        self.temperature_frame = QtWidgets.QFrame(self.centralwidget)
        self.temperature_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.temperature_frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.temperature_frame.setObjectName("temperature_frame")
        self.gridLayout_5 = QtWidgets.QGridLayout(self.temperature_frame)
        self.gridLayout_5.setObjectName("gridLayout_5")
        self.temperature_current_setpoint_label = QtWidgets.QLabel(
            self.temperature_frame
        )
        self.temperature_current_setpoint_label.setObjectName(
            "temperature_current_setpoint_label"
        )
        self.gridLayout_5.addWidget(
            self.temperature_current_setpoint_label, 3, 0, 1, 2
        )
        self.temperature_measurement_lcd = QtWidgets.QLCDNumber(
            self.temperature_frame
        )
        self.temperature_measurement_lcd.setObjectName(
            "temperature_measurement_lcd"
        )
        self.gridLayout_5.addWidget(
            self.temperature_measurement_lcd, 4, 2, 1, 2
        )
        self.temperature_setpoint_label = QtWidgets.QLabel(
            self.temperature_frame
        )
        self.temperature_setpoint_label.setObjectName(
            "temperature_setpoint_label"
        )
        self.gridLayout_5.addWidget(self.temperature_setpoint_label, 2, 0, 1, 1)
        self.temperature_measurement_label = QtWidgets.QLabel(
            self.temperature_frame
        )
        self.temperature_measurement_label.setObjectName(
            "temperature_measurement_label"
        )
        self.gridLayout_5.addWidget(
            self.temperature_measurement_label, 4, 0, 1, 2
        )
        self.temperature_setpoint_lcd = QtWidgets.QLCDNumber(
            self.temperature_frame
        )
        self.temperature_setpoint_lcd.setObjectName("temperature_setpoint_lcd")
        self.gridLayout_5.addWidget(self.temperature_setpoint_lcd, 3, 2, 1, 2)
        self.line = QtWidgets.QFrame(self.temperature_frame)
        self.line.setFrameShape(QtWidgets.QFrame.HLine)
        self.line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line.setObjectName("line")
        self.gridLayout_5.addWidget(self.line, 1, 0, 1, 4)
        self.temperature_label = QtWidgets.QLabel(self.temperature_frame)
        self.temperature_label.setObjectName("temperature_label")
        self.gridLayout_5.addWidget(self.temperature_label, 0, 0, 1, 1)
        self.temperature_setpoint_btn = QtWidgets.QPushButton(
            self.temperature_frame
        )
        self.temperature_setpoint_btn.setObjectName("temperature_setpoint_btn")
        self.gridLayout_5.addWidget(self.temperature_setpoint_btn, 2, 3, 1, 1)
        self.temperature_setpoint_spinbox = QtWidgets.QDoubleSpinBox(
            self.temperature_frame
        )
        self.temperature_setpoint_spinbox.setObjectName(
            "temperature_setpoint_spinbox"
        )
        self.gridLayout_5.addWidget(
            self.temperature_setpoint_spinbox, 2, 1, 1, 2
        )
        self.gridLayout_7.addWidget(self.temperature_frame, 0, 0, 1, 1)
        self.start_stop_frame = QtWidgets.QFrame(self.centralwidget)
        self.start_stop_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.start_stop_frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.start_stop_frame.setObjectName("start_stop_frame")
        self.gridLayout = QtWidgets.QGridLayout(self.start_stop_frame)
        self.gridLayout.setObjectName("gridLayout")
        self.start_control_btn = QtWidgets.QPushButton(self.start_stop_frame)
        self.start_control_btn.setObjectName("start_control_btn")
        self.gridLayout.addWidget(self.start_control_btn, 0, 0, 1, 1)
        self.stop_control_btn = QtWidgets.QPushButton(self.start_stop_frame)
        self.stop_control_btn.setObjectName("stop_control_btn")
        self.gridLayout.addWidget(self.stop_control_btn, 0, 1, 1, 1)
        self.gridLayout_7.addWidget(self.start_stop_frame, 2, 0, 1, 2)
        self.history_frame = QtWidgets.QFrame(self.centralwidget)
        self.history_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.history_frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.history_frame.setObjectName("history_frame")
        self.gridLayout_3 = QtWidgets.QGridLayout(self.history_frame)
        self.gridLayout_3.setObjectName("gridLayout_3")
        # EDIT BETWEEN HERE
        self.history_graphics = pg.PlotWidget(self.history_frame)
        # AND HERE
        self.history_graphics.setObjectName("history_graphics")
        self.gridLayout_3.addWidget(self.history_graphics, 1, 0, 1, 1)
        self.history_label = QtWidgets.QLabel(self.history_frame)
        self.history_label.setObjectName("history_label")
        self.gridLayout_3.addWidget(self.history_label, 0, 0, 1, 1)
        self.gridLayout_7.addWidget(self.history_frame, 0, 1, 1, 1)
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 577, 22))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "Brewpi 5000"))
        self.radio_pump_on.setText(_translate("MainWindow", "På"))
        self.pump_label.setText(_translate("MainWindow", "Pumpe"))
        self.radio_pump_off.setText(_translate("MainWindow", "Av"))
        self.control_technique_label.setText(
            _translate("MainWindow", "Reguleringsteknikk")
        )
        self.temperature_current_setpoint_label.setText(
            _translate("MainWindow", "Nåværende setpoint")
        )
        self.temperature_setpoint_label.setText(
            _translate("MainWindow", "Setpoint")
        )
        self.temperature_measurement_label.setText(
            _translate("MainWindow", "Temperatur i kjele")
        )
        self.temperature_label.setText(_translate("MainWindow", "Temperatur"))
        self.temperature_setpoint_btn.setText(_translate("MainWindow", "Ok"))
        self.start_control_btn.setText(
            _translate("MainWindow", "Start regulering")
        )
        self.stop_control_btn.setText(
            _translate("MainWindow", "Stopp regulering")
        )
        self.history_label.setText(_translate("MainWindow", "Historikk"))
        # Auto-generated code stops here


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    ui = Ui_MainWindow()
    ui.show()
    sys.exit(app.exec_())
