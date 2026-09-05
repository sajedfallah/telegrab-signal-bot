/// <reference types="vite/client" />
interface Window { Telegram?: { WebApp: { initData:string; colorScheme:string; ready():void; expand():void; close():void; openTelegramLink(url:string):void; HapticFeedback?:{impactOccurred(style:string):void}; } } }
