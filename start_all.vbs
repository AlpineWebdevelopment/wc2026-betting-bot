Set oShell = CreateObject("WScript.Shell")

Dim py
py = "C:\Users\user\AppData\Local\Python\bin\python.exe"

' Start Flask server (hidden window)
oShell.Run """" & py & """ """ & "C:\severinnhq\sportsbetting\app.py""", 0, False

' Wait for server to boot before starting bot
WScript.Sleep 8000

' Start Telegram bot (hidden window)
oShell.Run """" & py & """ """ & "C:\severinnhq\sportsbetting\telegram_bot.py""", 0, False
