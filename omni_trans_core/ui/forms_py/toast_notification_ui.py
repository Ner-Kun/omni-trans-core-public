# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'toast_notification.ui'
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
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSpacerItem, QWidget)

class Ui_ToastNotification(object):
    def setupUi(self, ToastNotification):
        if not ToastNotification.objectName():
            ToastNotification.setObjectName(u"ToastNotification")
        ToastNotification.resize(400, 60)
        ToastNotification.setFrameShape(QFrame.StyledPanel)
        ToastNotification.setFrameShadow(QFrame.Raised)
        self.horizontalLayout = QHBoxLayout(ToastNotification)
        self.horizontalLayout.setSpacing(10)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(12, 8, 12, 8)
        self.icon_label = QLabel(ToastNotification)
        self.icon_label.setObjectName(u"icon_label")
        self.icon_label.setMinimumSize(QSize(24, 24))
        self.icon_label.setMaximumSize(QSize(24, 24))
        self.icon_label.setAlignment(Qt.AlignCenter)

        self.horizontalLayout.addWidget(self.icon_label)

        self.text_label = QLabel(ToastNotification)
        self.text_label.setObjectName(u"text_label")
        self.text_label.setWordWrap(True)

        self.horizontalLayout.addWidget(self.text_label)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.action_button = QPushButton(ToastNotification)
        self.action_button.setObjectName(u"action_button")
        self.action_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.horizontalLayout.addWidget(self.action_button)

        self.close_button = QPushButton(ToastNotification)
        self.close_button.setObjectName(u"close_button")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.close_button.sizePolicy().hasHeightForWidth())
        self.close_button.setSizePolicy(sizePolicy)
        self.close_button.setMinimumSize(QSize(20, 20))
        self.close_button.setMaximumSize(QSize(20, 20))
        self.close_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.horizontalLayout.addWidget(self.close_button)


        self.retranslateUi(ToastNotification)

        QMetaObject.connectSlotsByName(ToastNotification)
    # setupUi

    def retranslateUi(self, ToastNotification):
        ToastNotification.setWindowTitle(QCoreApplication.translate("ToastNotification", u"Toast", None))
        self.icon_label.setText(QCoreApplication.translate("ToastNotification", u"\u2139\ufe0f", None))
        self.text_label.setText(QCoreApplication.translate("ToastNotification", u"Notification text", None))
        self.action_button.setText(QCoreApplication.translate("ToastNotification", u"Action", None))
        self.close_button.setText("")
#if QT_CONFIG(tooltip)
        self.close_button.setToolTip(QCoreApplication.translate("ToastNotification", u"Close", None))
#endif // QT_CONFIG(tooltip)
    # retranslateUi

