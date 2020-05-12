from datetime import datetime
import os
import time

from PyQt5.QtWidgets import *
from PyQt5.QtCore import QThread
from PyQt5 import uic

from ui.codeeditor import CodeEditor, AssemblyHighlighter
from ui.models import (RegistersModel, FlagModel, CodeSegModel, StackSegModel, DataSegModel)

import re
import sys
import queue
from emulator.assembler import Assembler
from emulator.memory import Memory
from emulator.pipeline_units import bus_interface_unit, execution_unit
from emulator.cpu import CPU

INSTRUCTION_QUEUE_SIZE = 6
MEMORY_SIZE = int('FFFFF', 16)  # 内存空间大小 1MB
CACHE_SIZE = int('10000', 16)  # 缓存大小 64KB
SEGMENT_SIZE = int('10000', 16) # 段长度均为最大长度64kB（10000H）

SEG_INIT = {
    'DS': int('2000', 16), # Initial value of data segment
    'CS': int('3000', 16), # Initial value of code segment
    'SS': int('5000', 16), # Initial value of stack segment
    'ES': int('7000', 16) # Initial value of extra segment
}


def _resource(*rsc):
    directory = os.path.dirname(__file__)
    return os.path.join(directory, *rsc)

class MainWindow(object):
    def __init__(self, qApp=None):

        self.gui = uic.loadUi(_resource('mainwindow.ui'))
        # Assembly editor get focus on start
        self.asmEdit = self.gui.findChild(CodeEditor, "asmEdit")
        # Get console area
        self.console = self.gui.findChild(QPlainTextEdit, "txtConsole")

        self.assembler = Assembler(SEG_INIT)
        self.memory = Memory(MEMORY_SIZE, SEGMENT_SIZE)

        # self.exe_file = self.assembler.compile(open(_resource('default.asm')).read())
        self.asmEdit.setPlainText(open(_resource('default.asm')).read())

        self.BIU = bus_interface_unit.bus_interface_unit(INSTRUCTION_QUEUE_SIZE, self.assembler, self.memory, self.console)
        self.EU = execution_unit.execution_unit(self.BIU, self.console)
        self.cpu = CPU(self.BIU, self.EU, self.console)

        qApp.lastWindowClosed.connect(self.stopAndWait)
        self.setupEditorAndDiagram()
        self.setupSplitters()
        self.setupModels()
        self.setupTrees()
        self.setupActions()

    def setupEditorAndDiagram(self):
        # self.asmEdit = QPlainTextEdit()
        self.asmEdit.setFocus()
        self.asmEdit.setStyleSheet("""QPlainTextEdit{
            font-family:'Consolas'; 
            color: #ccc; 
            background-color: #2b2b2b;}""")
        self.highlight = AssemblyHighlighter(self.asmEdit.document())


    def setupSplitters(self):
        mainsplitter = self.gui.findChild(QSplitter, "mainsplitter")
        mainsplitter.setStretchFactor(0, 5)
        mainsplitter.setStretchFactor(1, 12)
        mainsplitter.setStretchFactor(2, 4)
        mainsplitter.setStretchFactor(3, 4)

        leftsplitter = self.gui.findChild(QSplitter, "leftsplitter")
        leftsplitter.setStretchFactor(0, 5)
        leftsplitter.setStretchFactor(1, 4)
        leftsplitter.setStretchFactor(2, 4)

        middlesplitter = self.gui.findChild(QSplitter, "middlesplitter")
        middlesplitter.setStretchFactor(0, 2)
        middlesplitter.setStretchFactor(1, 1)

    def setupModels(self):
        self.genRegsModel = RegistersModel(self.cpu.EU, (
                'AX', 'BX', 'CX', 'DX', 'SP', 'BP', 'SI', 'DI',
            ))
        self.specRegsModel = RegistersModel(self.cpu.BIU, (
                'DS', 'CS', 'SS', 'ES', 'IP',
            ))
        self.stateRegsModel = FlagModel(self.cpu.EU, (
                'CF', 'PF', 'AF', 'Z', 'S', 'O', 'TF', 'IF', 'DF',
            ))
        self.CodeSegModel = CodeSegModel(self.BIU, self.BIU.reg['IP'])
        self.StackSegModel = StackSegModel(self.BIU, self.EU.reg['SP'])
        self.DataSegModel = DataSegModel(self.BIU)

    def setupTrees(self):
        treeGenericRegs = self.gui.findChild(QTreeView, "treeGenericRegs")
        treeGenericRegs.setModel(self.genRegsModel)
        treeGenericRegs.expandAll()
        treeGenericRegs.resizeColumnToContents(0)
        treeGenericRegs.resizeColumnToContents(1)

        treeSpecificRegs = self.gui.findChild(QTreeView, "treeSpecificRegs")
        treeSpecificRegs.setModel(self.specRegsModel)
        treeSpecificRegs.expandAll()
        treeSpecificRegs.resizeColumnToContents(0)
        treeSpecificRegs.resizeColumnToContents(1)

        treeStateRegs = self.gui.findChild(QTreeView, "treeStateRegs")
        treeStateRegs.setModel(self.stateRegsModel)
        treeStateRegs.expandAll()
        treeStateRegs.resizeColumnToContents(0)
        treeStateRegs.resizeColumnToContents(1)

        # memory
        self.treeMemory = self.gui.findChild(QTreeView, "treeMemory")
        treeMemory = self.treeMemory
        treeMemory.setModel(self.CodeSegModel)
        treeMemory.resizeColumnToContents(0)
        treeMemory.resizeColumnToContents(1)

        self.treeMemory2 = self.gui.findChild(QTreeView, "treeMemory2")
        treeMemory2 = self.treeMemory2
        treeMemory2.setModel(self.StackSegModel)
        treeMemory2.resizeColumnToContents(0)
        treeMemory2.resizeColumnToContents(1)

        self.treeMemory3 = self.gui.findChild(QTreeView, "treeMemory3")
        treeMemory3 = self.treeMemory3
        treeMemory3.setModel(self.DataSegModel)
        treeMemory3.resizeColumnToContents(0)
        treeMemory3.resizeColumnToContents(1)

    def setupActions(self):
        self.actionLoad = self.gui.findChild(QAction, "actionLoad")
        self.actionLoad.triggered.connect(self.loadAssembly)

        self.actionRun = self.gui.findChild(QAction, "actionRun")
        self.actionRun.triggered.connect(self.runAction)

        self.actionStep = self.gui.findChild(QAction, "actionStep")
        self.actionStep.triggered.connect(self.nextInstruction)

        self.actionStop = self.gui.findChild(QAction, "actionStop")
        self.actionStop.triggered.connect(self.stopAction)

        self.actionOpen = self.gui.findChild(QAction, "actionOpen")
        self.actionOpen.triggered.connect(self.openAction)

    def loadAssembly(self):
        # Enable/Disable actions
        self.actionLoad.setEnabled(False)
        self.actionRun.setEnabled(True)
        self.actionStep.setEnabled(True)
        self.actionStop.setEnabled(True)
        editor = self.asmEdit
        editor.setReadOnly()

        assembly = editor.toPlainText()
        if not assembly:
            self.console.appendPlainText("Input Error.")
            self.restoreEditor()
            return
        self.exe_file = self.assembler.compile(assembly)
        self.memory.load(self.exe_file)  # load code segment
        self.BIU = bus_interface_unit.bus_interface_unit(INSTRUCTION_QUEUE_SIZE, self.exe_file, self.memory, self.console)
        self.EU = execution_unit.execution_unit(self.BIU, self.console)
        self.cpu = CPU(self.BIU, self.EU, self.console)
        self.refreshModels()

        self.console.appendPlainText("Initial DS: " + hex(self.BIU.reg['DS']))
        self.console.appendPlainText("Initial CS: " + hex(self.BIU.reg['CS']))
        self.console.appendPlainText("Initial SS: " + hex(self.BIU.reg['SS']))
        self.console.appendPlainText("Initial ES: " + hex(self.BIU.reg['ES']))
        self.console.appendPlainText("Initial IP: " + hex(self.BIU.reg['IP']))
        self.console.appendPlainText("CPU initialized successfully.")


    def runAction(self):
        self.actionRun.setEnabled(False)
        self.actionStep.setEnabled(False)

        while not self.cpu.check_done():
            self.cpu.iterate(debug=False)
            self.refreshModels()
            time.sleep(0.3)
        self.cpu.print_end_state()
        self.stopAction()

    def nextInstruction(self):
        if not self.cpu.check_done():
            self.cpu.iterate(debug=False)
            self.refreshModels()
        else:
            self.cpu.print_end_state()
            self.stopAction()

    def stopAndWait(self):
        # Stop correctly
        # self.cpu.stop()
        # if self.emitter is not None:
        #     self.emitter.wait()
        return

    def stopAction(self):
        self.stopAndWait()
        self.restoreEditor()

    def openAction(self):
        self.stopAction()
        filename = QFileDialog().getOpenFileName(self.gui, "Open File")[0]
        if os.path.exists(filename) and self.asmEdit.document().isModified():
            answer = QMessageBox.question(self.gui, "Modified Code",
                """<b>The current code is modified</b>
                   <p>What do you want to do?</p>
                """,
                QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Cancel)
            if answer == QMessageBox.Cancel:
                return

        self.asmEdit.setPlainText(open(filename, encoding='utf-8').read())
        self.restoreEditor()

    def restoreEditor(self):
        # Enable/Disable actions
        self.actionLoad.setEnabled(True)
        self.actionRun.setEnabled(False)
        self.actionStep.setEnabled(False)
        self.actionStop.setEnabled(False)
        # Re-enable editor
        self.asmEdit.setReadOnly(False)
        self.asmEdit.setFocus()
        self.refreshModels()

    def refreshModels(self):
        self.ip = self.BIU.reg['IP']
        self.sp = self.EU.reg['SP']
        self.setupModels()
        self.setupTrees()

    def show(self):
        self.gui.show()
