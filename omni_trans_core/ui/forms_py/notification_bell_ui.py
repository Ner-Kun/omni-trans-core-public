# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'notification_bell.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QPushButton, QSizePolicy, QWidget)

class Ui_NotificationBell(object):
    def setupUi(self, NotificationBell):
        if not NotificationBell.objectName():
            NotificationBell.setObjectName(u"NotificationBell")
        NotificationBell.resize(40, 30)
        NotificationBell.setMinimumSize(QSize(40, 30))
        NotificationBell.setMaximumSize(QSize(50, 30))
        NotificationBell.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        NotificationBell.setFlat(True)

        self.retranslateUi(NotificationBell)

        QMetaObject.connectSlotsByName(NotificationBell)
    # setupUi

    def retranslateUi(self, NotificationBell):
        NotificationBell.setText(QCoreApplication.translate("NotificationBell", u"\U0001f514", None))
    # retranslateUi

