import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { GoogleGenAI, GenerateContentResponse } from "@google/genai";

// --- Styles & Theme ---
const theme = {
  bg: '#17212b',
  chatBg: '#0e1621',
  headerBg: '#17212b',
  inputBg: '#17212b',
  userMsg: '#2b5278',
  botMsg: '#182533',
  text: '#ffffff',
  accent: '#5288c1',
  secondaryText: '#7f91a4',
  border: '#0e1621',
  codeBg: '#2b2b2b',
  success: '#4caf50'
};

const styles = {
  appContainer: {
    display: 'flex',
    height: '100vh',
    width: '100vw',
    backgroundColor: theme.bg,
    overflow: 'hidden',
  },
  sidebar: {
    width: '350px',
    borderRight: `1px solid ${theme.border}`,
    display: 'flex',
    flexDirection: 'column' as const,
    backgroundColor: theme.headerBg,
    zIndex: 10,
  },
  mainContent: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    position: 'relative' as const,
    backgroundColor: theme.chatBg,
    backgroundImage: 'url("https://web.telegram.org/img/bg_0.png")', 
    backgroundSize: 'auto',
  },
  header: {
    padding: '10px 20px',
    backgroundColor: theme.headerBg,
    borderBottom: `1px solid ${theme.border}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: '60px',
  },
  avatar: {
    width: '40px',
    height: '40px',
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #6a11cb 0%, #2575fc 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '18px',
    fontWeight: 'bold',
    marginRight: '15px',
  },
  chatArea: {
    flex: 1,
    overflowY: 'auto' as const,
    padding: '20px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '10px',
  },
  messageRow: (isUser: boolean) => ({
    display: 'flex',
    justifyContent: isUser ? 'flex-end' : 'flex-start',
    marginBottom: '5px',
  }),
  messageBubble: (isUser: boolean) => ({
    backgroundColor: isUser ? theme.userMsg : theme.botMsg,
    padding: '8px 12px',
    borderRadius: '8px',
    maxWidth: '70%',
    boxShadow: '0 1px 2px rgba(0,0,0,0.3)',
    position: 'relative' as const,
    borderBottomRightRadius: isUser ? '0' : '8px',
    borderBottomLeftRadius: isUser ? '8px' : '0',
  }),
  inputArea: {
    padding: '10px 20px',
    backgroundColor: theme.headerBg,
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  input: {
    flex: 1,
    backgroundColor: '#242f3d',
    border: 'none',
    borderRadius: '20px',
    padding: '12px 20px',
    color: 'white',
    fontSize: '16px',
    outline: 'none',
  },
  sendButton: {
    background: 'none',
    border: 'none',
    color: theme.accent,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  infoPanel: {
    padding: '20px',
    color: theme.secondaryText,
    fontSize: '14px',
    borderBottom: `1px solid ${theme.border}`,
  },
  calendarPreview: {
    padding: '20px',
    flex: 1,
    overflowY: 'auto' as const,
  },
  slotGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(5, 1fr)',
    gap: '5px',
    marginTop: '10px',
  },
  dayColumn: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '5px',
  },
  timeSlot: (status: 'free' | 'busy' | 'unknown') => ({
    height: '30px',
    backgroundColor: status === 'free' ? '#4caf50' : status === 'busy' ? '#e53935' : '#2b5278',
    borderRadius: '4px',
    fontSize: '10px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'white',
    opacity: status === 'unknown' ? 0.3 : 1,
  }),
  docContainer: {
    padding: '40px',
    overflowY: 'auto' as const,
    flex: 1,
    backgroundColor: '#1e1e1e',
    color: '#d4d4d4',
    fontFamily: 'monospace',
  },
  codeBlock: {
    backgroundColor: '#2d2d2d',
    padding: '15px',
    borderRadius: '5px',
    overflowX: 'auto' as const,
    marginBottom: '20px',
    border: '1px solid #444',
    fontSize: '14px',
    lineHeight: '1.5',
  },
  sectionTitle: {
    color: theme.accent,
    marginTop: '30px',
    marginBottom: '10px',
    borderBottom: '1px solid #444',
    paddingBottom: '5px',
    fontSize: '20px'
  },
  toggleButton: {
    marginTop: '10px',
    backgroundColor: theme.accent,
    color: 'white',
    border: 'none',
    padding: '8px 12px',
    borderRadius: '4px',
    cursor: 'pointer',
    width: '100%',
    fontWeight: 'bold'
  }
};

// --- Types ---
type Message = {
  id: string;
  text: string;
  isUser: boolean;
  timestamp: number;
};

type SlotStatus = 'free' | 'busy' | 'unknown';

// --- Mock Data & Utilities ---
const generateWeekData = () => {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
  const hours = [9, 10, 11, 12, 13, 14, 15, 16, 17];
  return days.map(day => ({
    name: day,
    slots: hours.map(h => ({
      time: `${h}:00`,
      status: Math.random() > 0.6 ? 'busy' : 'free' as SlotStatus
    }))
  }));
};

const INITIAL_QUESTIONS = [
  "Привет! Я прототип твоего Календарь-бота.",
  "Я обновил интерфейс. Теперь справа доступен 'Режим разработчика' с планом и кодом для бэкенда.",
  "Для симуляции работы ответь на вопросы:",
  "1. ID календаря (твой email)?",
  "2. Часовой пояс?",
  "3. Рабочие часы?"
];

// --- Components ---

const ChatMessage: React.FC<{ msg: Message }> = ({ msg }) => (
  <div style={styles.messageRow(msg.isUser)}>
    <div style={styles.messageBubble(msg.isUser)}>
      <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>
      <div style={{ 
        fontSize: '10px', 
        color: 'rgba(255,255,255,0.5)', 
        textAlign: 'right', 
        marginTop: '4px' 
      }}>
        {new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
      </div>
    </div>
  </div>
);

const CalendarVisualizer = ({ data }: { data: any[] }) => {
  return (
    <div style={styles.calendarPreview}>
      <h3 style={{ color: theme.text, margin: '0 0 15px 0' }}>Calendar Preview (Week)</h3>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
        <div style={{display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px', color: theme.secondaryText}}>
          <div style={{width: 10, height: 10, backgroundColor: '#4caf50', borderRadius: 2}}></div> Free
        </div>
        <div style={{display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px', color: theme.secondaryText}}>
          <div style={{width: 10, height: 10, backgroundColor: '#e53935', borderRadius: 2}}></div> Busy
        </div>
      </div>
      <div style={styles.slotGrid}>
        {data.map((day, i) => (
          <div key={i} style={styles.dayColumn}>
            <div style={{ textAlign: 'center', fontSize: '12px', color: theme.secondaryText, marginBottom: '5px' }}>
              {day.name}
            </div>
            {day.slots.map((slot: any, j: number) => (
              <div key={j} style={styles.timeSlot(slot.status)} title={`${day.name} ${slot.time}`}>
                {slot.time}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};

const DocsView = () => (
  <div style={styles.docContainer}>
    <h1>🚀 План реализации Бэкенда</h1>
    <p>Для работы с приватными ключами и API Google нужен сервер. Браузерный JS не подойдет из-за безопасности.</p>

    <h2 style={styles.sectionTitle}>Шаг 1: Подготовка проекта (Node.js)</h2>
    <p>Создайте папку, инициализируйте проект и установите зависимости.</p>
    <pre style={styles.codeBlock}>{`mkdir calendar-bot
cd calendar-bot
npm init -y
npm install googleapis telegraf dotenv date-fns`}</pre>
    <p>Создайте файл <code>.env</code> и поместите туда токен бота и ID календаря.</p>

    <h2 style={styles.sectionTitle}>Шаг 2: Подключение к Google Calendar</h2>
    <p>Используем библиотеку <code>googleapis</code> и ваш JSON-ключ сервисного аккаунта (файл <code>service-account.json</code>).</p>
    <pre style={styles.codeBlock}>{`const { google } = require('googleapis');
const key = require('./service-account.json'); // Ваш JSON файл

const jwtClient = new google.auth.JWT(
  key.client_email,
  null,
  key.private_key,
  ['https://www.googleapis.com/auth/calendar.readonly']
);

const calendar = google.calendar({ version: 'v3', auth: jwtClient });`}</pre>

    <h2 style={styles.sectionTitle}>Шаг 3: Логика поиска слотов</h2>
    <p>Функция получает события и ищет "дырки" в расписании.</p>
    <pre style={styles.codeBlock}>{`async function getFreeSlots(calendarId, startHour = 9, endHour = 18) {
  const now = new Date();
  const endOfDay = new Date();
  endOfDay.setHours(endHour, 0, 0);

  // 1. Получаем занятые слоты
  const res = await calendar.events.list({
    calendarId: calendarId,
    timeMin: now.toISOString(),
    timeMax: endOfDay.toISOString(),
    singleEvents: true,
    orderBy: 'startTime',
  });

  const busySlots = res.data.items.map(event => ({
    start: new Date(event.start.dateTime || event.start.date),
    end: new Date(event.end.dateTime || event.end.date)
  }));

  // 2. Вычисляем свободные окна (упрощенно)
  let currentPointer = new Date();
  currentPointer.setHours(startHour, 0, 0);
  if (currentPointer < now) currentPointer = now; // Не ищем в прошлом

  const freeSlots = [];
  
  // Простая логика перебора часов
  while (currentPointer.getHours() < endHour) {
    const nextHour = new Date(currentPointer);
    nextHour.setHours(currentPointer.getHours() + 1);

    const isBusy = busySlots.some(slot => 
      (currentPointer >= slot.start && currentPointer < slot.end) ||
      (nextHour > slot.start && nextHour <= slot.end)
    );

    if (!isBusy) {
      freeSlots.push(\`\${currentPointer.getHours()}:00 - \${nextHour.getHours()}:00\`);
    }
    currentPointer = nextHour;
  }
  
  return freeSlots;
}`}</pre>

    <h2 style={styles.sectionTitle}>Шаг 4: Telegram Бот (Telegraf)</h2>
    <p>Соединяем все вместе.</p>
    <pre style={styles.codeBlock}>{`const { Telegraf } = require('telegraf');
const bot = new Telegraf(process.env.BOT_TOKEN);

bot.command('start', (ctx) => ctx.reply('Привет! Напиши /free чтобы найти время.'));

bot.command('free', async (ctx) => {
  try {
    ctx.reply('🔍 Ищу свободные слоты...');
    const slots = await getFreeSlots(process.env.CALENDAR_ID);
    if (slots.length > 0) {
      ctx.reply('✅ Свободное время на сегодня:\\n' + slots.join('\\n'));
    } else {
      ctx.reply('😔 Сегодня все забито.');
    }
  } catch (e) {
    console.error(e);
    ctx.reply('Ошибка доступа к календарю.');
  }
});

bot.launch();`}</pre>
  </div>
);

const App = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [calendarData, setCalendarData] = useState(generateWeekData());
  const [isTyping, setIsTyping] = useState(false);
  const [viewMode, setViewMode] = useState<'chat' | 'docs'>('chat');
  
  const chatEndRef = useRef<HTMLDivElement>(null);
  const ai = useRef(new GoogleGenAI({ apiKey: process.env.API_KEY })).current;

  useEffect(() => {
    const introMsgs = INITIAL_QUESTIONS.map((text, i) => ({
      id: `init-${i}`,
      text,
      isUser: false,
      timestamp: Date.now() + i * 100
    }));
    setMessages(introMsgs);
  }, []);

  useEffect(() => {
    if (viewMode === 'chat') {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, viewMode]);

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      text: inputValue,
      isUser: true,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsTyping(true);

    try {
      const chat = ai.chats.create({
        model: 'gemini-2.5-flash',
        config: {
          systemInstruction: `You are a Telegram Bot prototype named "NoBugs Calendar Bot". 
        The user wants to find free slots in their Google Calendar.
        
        Current Context:
        - You are a Frontend Simulator. You cannot actually access Google Calendar API directly.
        - You have been provided with Service Account credentials (project: nobugs-478214).
        - If the user asks about implementation details, tell them to click the "Developer Mode" button in the sidebar.
        - Be helpful, concise, and act like a Telegram Bot.`
        },
        history: messages.map(m => ({
          role: m.isUser ? 'user' : 'model',
          parts: [{ text: m.text }]
        }))
      });

      const result = await chat.sendMessage({ message: userMsg.text });
      
      if (userMsg.text.toLowerCase().includes('find') || userMsg.text.toLowerCase().includes('free')) {
        setCalendarData(generateWeekData());
      }

      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        text: result.text,
        isUser: false,
        timestamp: Date.now()
      };
      
      setMessages(prev => [...prev, botMsg]);
    } catch (error) {
      console.error(error);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSend();
  };

  return (
    <div style={styles.appContainer}>
      {/* Sidebar / Config Panel */}
      <div style={styles.sidebar}>
        <div style={styles.header}>
          <span style={{ fontWeight: 500, fontSize: '18px' }}>Menu</span>
        </div>
        
        <div style={styles.infoPanel}>
          <button 
            style={{
              ...styles.toggleButton,
              backgroundColor: viewMode === 'chat' ? '#2b5278' : theme.accent
            }}
            onClick={() => setViewMode(viewMode === 'chat' ? 'docs' : 'chat')}
          >
            {viewMode === 'chat' ? '🛠 Switch to Developer Mode' : '💬 Back to Chat Simulator'}
          </button>

          <div style={{ marginTop: '15px' }}>
            <div style={{ marginBottom: '5px', fontWeight: 'bold', color: theme.text }}>Status</div>
            <div style={{ fontSize: '12px', color: theme.secondaryText }}>
              Environment: <span style={{ color: theme.accent }}>Prototype</span>
            </div>
            <div style={{ fontSize: '12px', color: theme.secondaryText }}>
              Service Account: <span style={{ color: styles.timeSlot('free').backgroundColor }}>Connected</span>
            </div>
          </div>
        </div>

        {viewMode === 'chat' && <CalendarVisualizer data={calendarData} />}
      </div>

      {/* Main Content Area (Chat or Docs) */}
      {viewMode === 'chat' ? (
        <div style={styles.mainContent}>
          <div style={styles.header}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <div style={styles.avatar}>NB</div>
              <div>
                <div style={{ fontWeight: 'bold', fontSize: '16px' }}>NoBugs Calendar Bot</div>
                <div style={{ fontSize: '13px', color: theme.accent }}>bot</div>
              </div>
            </div>
            <div style={{ color: theme.secondaryText }}>
              <span className="material-symbols-outlined" style={{ cursor: 'pointer' }}>more_vert</span>
            </div>
          </div>

          <div style={styles.chatArea}>
            {messages.map(msg => (
              <ChatMessage key={msg.id} msg={msg} />
            ))}
            {isTyping && (
              <div style={{...styles.messageRow(false), opacity: 0.7}}>
                <div style={styles.messageBubble(false)}>Typing...</div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div style={styles.inputArea}>
            <span className="material-symbols-outlined" style={{ color: theme.secondaryText, cursor: 'pointer' }}>attach_file</span>
            <input
              style={styles.input}
              placeholder="Write a message..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
            />
            <button style={styles.sendButton} onClick={handleSend}>
              <span className="material-symbols-outlined" style={{ fontSize: '28px' }}>send</span>
            </button>
          </div>
        </div>
      ) : (
        <DocsView />
      )}
    </div>
  );
};

const container = document.getElementById('root');
const root = createRoot(container!);
root.render(<App />);