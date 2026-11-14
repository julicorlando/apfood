COR = "#F26A0F"  # laranja da logo
COR_ESCURA = "#C9520A"
TEXTO = "#1D1D1F"

QSS = f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 14px; color: {TEXTO}; }}
QMainWindow, QDialog {{ background: #F6F6F4; }}
QLabel {{ color: {TEXTO}; background: transparent; }}
QCheckBox, QRadioButton, QGroupBox {{ color: {TEXTO}; }}
#menu {{ background: #1F2328; border: none; }}
#menu::item {{ color: #D0D4D9; padding: 14px 18px; border-left: 4px solid transparent; }}
#menu::item:selected {{ background: #2B3036; color: white; border-left: 4px solid {COR}; }}
QPushButton {{ background: white; color: {TEXTO}; border: 1px solid #D5D7DA; border-radius: 6px;
    padding: 8px 14px; }}
QPushButton:hover {{ border-color: {COR}; }}
QPushButton:default {{ border-color: {COR}; }}
QPushButton:disabled {{ color: #A0A4A8; background: #EEE; }}
QPushButton[papel="primario"] {{ background: {COR}; color: white; border: none; font-weight: 600; }}
QPushButton[papel="primario"]:hover {{ background: {COR_ESCURA}; }}
QPushButton[papel="link"] {{ background: transparent; border: none; color: {COR_ESCURA}; padding: 2px;
    text-decoration: underline; }}
QLabel[papel="rotulo"] {{ font-weight: 600; color: #3A3A3F; margin-top: 6px; }}
QLabel[papel="sutil"] {{ color: #6B6B70; font-size: 12px; }}
QLabel[papel="erro"] {{ background: #FBE9E7; color: #B3261E; border-radius: 6px; padding: 8px; }}
QFrame#cartaoLogin {{ background: white; border: 1px solid #E7E2DE; border-radius: 14px; }}
#cartaoLogin QLineEdit {{ padding: 9px; font-size: 15px; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {COR}; }}
QPushButton[papel="perigo"] {{ background: #C62828; color: white; border: none; }}
QPushButton[papel="produto"] {{ min-height: 70px; text-align: center; font-weight: 600; }}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{ background: white; border: 1px solid #D5D7DA; border-radius: 6px;
    padding: 6px; }}
QTableWidget {{ background: white; border: 1px solid #E1E3E5; gridline-color: #EEE; }}
QHeaderView::section {{ background: #F0F1F2; border: none; padding: 6px; font-weight: 600; }}
QLabel[papel="titulo"] {{ font-size: 20px; font-weight: 700; }}
QLabel[papel="total"] {{ font-size: 26px; font-weight: 800; color: {COR}; }}
QLabel[papel="aviso"] {{ background: #FFF4E5; border: 1px solid #FFB74D; border-radius: 6px; padding: 8px; }}
QFrame[papel="cartao"] {{ background: white; border: 1px solid #E1E3E5; border-radius: 8px; }}
QStatusBar {{ background: #1F2328; color: #D0D4D9; }}
"""
