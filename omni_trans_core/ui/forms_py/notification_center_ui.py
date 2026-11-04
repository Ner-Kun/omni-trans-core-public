# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'notification_center.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)

class Ui_NotificationCenter(object):
    def setupUi(self, NotificationCenter):
        if not NotificationCenter.objectName():
            NotificationCenter.setObjectName(u"NotificationCenter")
        NotificationCenter.resize(450, 500)
        NotificationCenter.setMinimumSize(QSize(350, 400))
        self.verticalLayout = QVBoxLayout(NotificationCenter)
        self.verticalLayout.setSpacing(10)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(15, 15, 15, 15)
        self.header_layout = QHBoxLayout()
        self.header_layout.setObjectName(u"header_layout")
        self.title_label = QLabel(NotificationCenter)
        self.title_label.setObjectName(u"title_label")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.title_label.setFont(font)

        self.header_layout.addWidget(self.title_label)

        self.header_spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.header_layout.addItem(self.header_spacer)

        self.filter_combo = QComboBox(NotificationCenter)
        self.filter_combo.setObjectName(u"filter_combo")
        self.filter_combo.setMinimumSize(QSize(150, 0))

        self.header_layout.addWidget(self.filter_combo)


        self.verticalLayout.addLayout(self.header_layout)

        self.notifications_list = QListWidget(NotificationCenter)
        self.notifications_list.setObjectName(u"notifications_list")
        self.notifications_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.notifications_list.setAlternatingRowColors(True)

        self.verticalLayout.addWidget(self.notifications_list)

        self.no_notifications_label = QLabel(NotificationCenter)
        self.no_notifications_label.setObjectName(u"no_notifications_label")
        self.no_notifications_label.setAlignment(Qt.AlignCenter)
        self.no_notifications_label.setStyleSheet(u"color: #888; font-style: italic;")

        self.verticalLayout.addWidget(self.no_notifications_label)

        self.button_layout = QHBoxLayout()
        self.button_layout.setObjectName(u"button_layout")
        self.button_spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.button_layout.addItem(self.button_spacer)

        self.clear_all_btn = QPushButton(NotificationCenter)
        self.clear_all_btn.setObjectName(u"clear_all_btn")

        self.button_layout.addWidget(self.clear_all_btn)


        self.verticalLayout.addLayout(self.button_layout)


        self.retranslateUi(NotificationCenter)

        QMetaObject.connectSlotsByName(NotificationCenter)
    # setupUi

    def retranslateUi(self, NotificationCenter):
        NotificationCenter.setWindowTitle(QCoreApplication.translate("NotificationCenter", u"Notifications", None))
        self.title_label.setText(QCoreApplication.translate("NotificationCenter", u"\U0001f514 Notifications", None))
        self.no_notifications_label.setText(QCoreApplication.translate("NotificationCenter", u"No notifications yet", None))
        self.clear_all_btn.setText(QCoreApplication.translate("NotificationCenter", u"Clear All", None))
    # retranslateUi

