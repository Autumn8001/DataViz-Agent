import React, { useState, useEffect, useRef } from 'react';
import { 
  Shield, User, Lock, LogIn, Send, Plus, 
  Trash2, Database, MessageSquare, UploadCloud, 
  ChevronRight, LogOut, Search, Activity, HelpCircle,
  FileSpreadsheet, Loader, CheckCircle2, Play, Code, AlertTriangle,
  RefreshCw
} from 'lucide-react';
import './App.css';

const RAG_AUTH_BASE = 'http://127.0.0.1:8000/api/v1/auth';
const AGENT_API_BASE = 'http://127.0.0.1:8001/api';
const IMAGE_SERVER_BASE = 'http://127.0.0.1:8001';

function App() {
  // --- 身份登录状态 (共享 RAG 用户) ---
  const [token, setToken] = useState(sessionStorage.getItem('token') || '');
  const [username, setUsername] = useState(sessionStorage.getItem('username') || '');
  const [tenantId, setTenantId] = useState(sessionStorage.getItem('tenant_id') || '');
  
  // 登录表单
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState('');

  // --- Agent 核心业务状态 ---
  const [sessions, setSessions] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeThreadId, setActiveThreadId] = useState('');
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [activeFilePath, setActiveFilePath] = useState('');
  const [isSending, setIsSending] = useState(false);

  // CSV/Excel 文件上传状态
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  // 运行过程中的轨道流状态
  const [currentStatus, setCurrentStatus] = useState('');
  const [currentTraceLogs, setCurrentTraceLogs] = useState([]);

  // 人在回路 (HITL) 状态
  const [isHitlSuspended, setIsHitlSuspended] = useState(false);

  const messagesEndRef = useRef(null);

  // 统一 SSO 登录
  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError('');

    try {
      const res = await fetch(`${RAG_AUTH_BASE}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: authUsername, password: authPassword })
      });
      const data = await res.json();
      if (res.ok) {
        setToken(data.access_token);
        setUsername(data.username);
        setTenantId(data.tenant_id);
        
        sessionStorage.setItem('token', data.access_token);
        sessionStorage.setItem('username', data.username);
        sessionStorage.setItem('tenant_id', data.tenant_id);

        // 新建全新 thread_id 并带有强隔离前缀
        const initialThreadId = `user_${data.username}_${Math.random().toString(36).substring(2, 14)}`;
        setActiveThreadId(initialThreadId);
        setMessages([]);
        setActiveFilePath('');
      } else {
        setAuthError(data.detail || '密码错误或用户未在 RAG 知识库系统中注册');
      }
    } catch (err) {
      setAuthError('连接 RAG 身份验证服务器失败 (8000 端口)，请确保后端正在运行');
    }
  };

  // 登出
  const handleLogout = () => {
    setToken('');
    setUsername('');
    setTenantId('');
    setSessions([]);
    setActiveThreadId('');
    setMessages([]);
    setActiveFilePath('');
    sessionStorage.clear();
  };

  // 初始化加载
  useEffect(() => {
    if (token) {
      fetchSessions();
    }
  }, [token]);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 获取会话列表
  const fetchSessions = async () => {
    try {
      const res = await fetch(`${AGENT_API_BASE}/sessions`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        const sorted = (data.data || []).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        setSessions(sorted);
      }
    } catch (err) {
      console.error('拉取历史对话失败', err);
    }
  };

  // 加载会话历史
  const handleSelectSession = async (threadId) => {
    setActiveThreadId(threadId);
    setMessages([]);
    setCurrentTraceLogs([]);
    setIsHitlSuspended(false);

    try {
      const res = await fetch(`${AGENT_API_BASE}/history/${threadId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok) {
        setMessages(data.data || []);
        setActiveFilePath(data.active_file_path || '');
        
        // 如果最后一条消息带有人在回路的关键字，直接自动唤醒 HITL 挂起状态
        const lastMsg = data.data?.[data.data.length - 1];
        if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content.includes('[人在回路中断拦截]')) {
          setIsHitlSuspended(true);
        }
      }
    } catch (err) {
      console.error('获取历史记录失败', err);
    }
  };

  // 开启新对话
  const handleCreateNewChat = () => {
    const nextThreadId = `user_${username}_${Math.random().toString(36).substring(2, 14)}`;
    setActiveThreadId(nextThreadId);
    setMessages([]);
    setActiveFilePath('');
    setCurrentTraceLogs([]);
    setIsHitlSuspended(false);
  };

  // 删除当前会话
  const handleDeleteSession = async (e, threadId) => {
    e.stopPropagation();
    if (!window.confirm('您确定要物理清空并删除该会话记录吗？')) return;
    try {
      const res = await fetch(`${AGENT_API_BASE}/history/${threadId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        if (activeThreadId === threadId) {
          handleCreateNewChat();
        }
        fetchSessions();
      }
    } catch (err) {
      console.error('删除会话失败', err);
    }
  };

  // 隔离数据源上传
  const handleUploadFile = async (file) => {
    if (!file) return;
    setIsUploading(true);
    setUploadProgress(`正在加密传输 ${file.name} 进入隔离沙箱...`);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${AGENT_API_BASE}/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        setActiveFilePath(data.file_path);
        setUploadProgress('');
        setIsUploading(false);
        alert(`数据源就绪: ${file.name}！可在下方输入分析需求。`);
      } else {
        alert(data.detail || '仅支持 CSV、XLSX、XLS 格式');
        setIsUploading(false);
      }
    } catch (err) {
      alert('连接分析服务异常');
      setIsUploading(false);
    }
  };

  // 拖拽文件支持
  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleUploadFile(files[0]);
    }
  };

  // 💡 正则处理图片本地物理路径到 API 静态地址映射
  const parseLocalImagePath = (text) => {
    if (!text) return '';
    // 将类似 ![alt](data/threads/xxx/output.png) 映射替换为绝对地址 http://localhost:8001/data/threads/xxx/output.png
    return text.replace(/!\[([^\]]*)\]\((data\/[^)]+)\)/g, (match, alt, path) => {
      return `![${alt}](${IMAGE_SERVER_BASE}/${path})`;
    });
  };

  // 双轨推流 SSE 逻辑与人在回路判断
  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || isSending) return;

    const userText = inputMessage;
    setInputMessage('');
    setIsSending(true);
    setCurrentStatus('⚙️ Agent 开始点火，意图识别中...');
    setCurrentTraceLogs([]);
    setIsHitlSuspended(false);

    // 将用户输入压入数组
    setMessages(prev => [...prev, { role: 'user', content: userText }]);
    // 占位
    setMessages(prev => [...prev, { role: 'assistant', content: '', trace_logs: [] }]);

    try {
      const res = await fetch(`${AGENT_API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          message: userText,
          file_path: activeFilePath || '',
          thread_id: activeThreadId
        })
      });

      if (!res.ok) {
        const errData = await res.json();
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: `[错误] ${errData.detail || '大模型生成失败'}` };
          return next;
        });
        setIsSending(false);
        setCurrentStatus('');
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let assistantText = '';
      let accumBuffer = '';
      let tempTraceLogs = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const textChunk = decoder.decode(value, { stream: true });
        accumBuffer += textChunk;

        // 分割行
        const lines = accumBuffer.split('\n');
        accumBuffer = lines.pop(); // 剩下一行不完整，留在下一次拼

        for (const line of lines) {
          const cleanLine = line.trim();
          if (cleanLine.startsWith('data: ')) {
            const dataStr = cleanLine.substring(6);
            if (dataStr === '[DONE]') break;

            try {
              const dataJson = JSON.parse(dataStr);

              // 1. Token 轨道 (吐字)
              if (dataJson.type === 'token') {
                assistantText += dataJson.content;
                setMessages(prev => {
                  const next = [...prev];
                  next[next.length - 1] = {
                    role: 'assistant',
                    content: assistantText,
                    trace_logs: tempTraceLogs
                  };
                  return next;
                });
              }
              // 2. Status 轨道 (气泡顶部状态播报)
              else if (dataJson.type === 'status') {
                setCurrentStatus(dataJson.content);
              }
              // 3. Trace 轨道 (执行日志与耗时)
              else if (dataJson.type === 'trace') {
                const traceObj = dataJson.content;
                tempTraceLogs = [...tempTraceLogs, traceObj];
                setCurrentTraceLogs(tempTraceLogs);

                setMessages(prev => {
                  const next = [...prev];
                  next[next.length - 1] = {
                    role: 'assistant',
                    content: assistantText,
                    trace_logs: tempTraceLogs
                  };
                  return next;
                });
              }
              // 4. Error 轨道
              else if (dataJson.type === 'error') {
                assistantText += `\n\n⚠️ **系统异常**: ${dataJson.content}\n\n`;
                setMessages(prev => {
                  const next = [...prev];
                  next[next.length - 1] = {
                    role: 'assistant',
                    content: assistantText,
                    trace_logs: tempTraceLogs
                  };
                  return next;
                });
              }
              // 5. Done 结束
              else if (dataJson.type === 'done') {
                break;
              }
            } catch (pErr) {
              // 忽略 JSON 解析噪音
            }
          }
        }
      }

      // 收尾检测是否进入了人在回路中断
      if (assistantText.includes('[人在回路中断拦截]')) {
        setIsHitlSuspended(true);
      }

      fetchSessions();
      setIsSending(false);
      setCurrentStatus('');
    } catch (err) {
      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: `[错误] 无法连接到大模型流式响应接口` };
        return next;
      });
      setIsSending(false);
      setCurrentStatus('');
    }
  };

  // 本地过滤会话
  const filteredSessions = sessions.filter(s => 
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // --- 登录页面设计 ---
  if (!token) {
    return (
      <div className="auth-wrapper">
        <div className="nebula-bg"></div>
        <div className="glass-card auth-container">
          <div className="auth-header">
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '14px' }}>
              <Shield size={38} color="var(--color-primary)" />
            </div>
            <h1>DataViz Agent</h1>
            <p>基于大厂准生产级的智能数据分析控制台</p>
          </div>

          <div className="sso-banner">
            <CheckCircle2 size={13} color="var(--color-success)" />
            <span>检测到统一 SSO 单点登录：请输入 RAG 系统账号</span>
          </div>

          <form onSubmit={handleLogin}>
            <div className="auth-form-group">
              <label>用户名</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type="text" 
                  className="neon-input" 
                  value={authUsername}
                  onChange={(e) => setAuthUsername(e.target.value)}
                  placeholder="请输入您的 RAG 账户名称" 
                  required
                />
                <User size={16} color="var(--text-muted)" style={{ position: 'absolute', right: '14px', top: '14px' }} />
              </div>
            </div>

            <div className="auth-form-group">
              <label>密码</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type="password" 
                  className="neon-input" 
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  placeholder="密码长度应 ≥ 6 位" 
                  required
                />
                <Lock size={16} color="var(--text-muted)" style={{ position: 'absolute', right: '14px', top: '14px' }} />
              </div>
            </div>

            <button type="submit" className="neon-btn" style={{ width: '100%', marginTop: '10px' }}>
              登录分析引擎并载入沙箱
            </button>
          </form>

          {authError && <div className="error-toast">{authError}</div>}
        </div>
      </div>
    );
  }

  // --- 主分析控制台渲染 ---
  return (
    <div className={`console-layout ${isHitlSuspended ? 'hitl-active' : ''}`}>
      <div className="nebula-bg"></div>

      {/* 1. 左侧历史会话侧边栏 */}
      <div className="sidebar-panel">
        <div className="sidebar-header">
          <Activity size={20} color="var(--color-primary)" />
          <h2>DataViz Agent</h2>
        </div>

        <button className="neon-btn new-chat-btn" onClick={handleCreateNewChat}>
          <Plus size={15} /> 新分析对话
        </button>

        <div className="search-box-wrapper">
          <input 
            type="text" 
            className="search-input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索历史分析需求..."
          />
          <Search size={14} className="search-icon" />
        </div>

        <div className="session-list">
          {filteredSessions.length === 0 ? (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', textAlign: 'center', marginTop: '10px' }}>
              暂无历史分析
            </span>
          ) : (
            filteredSessions.map(s => (
              <div 
                key={s.session_id} 
                className={`session-item ${activeThreadId === s.session_id ? 'active' : ''}`}
                onClick={() => handleSelectSession(s.session_id)}
              >
                <div className="session-info">
                  <MessageSquare size={14} color={activeThreadId === s.session_id ? 'var(--color-primary)' : 'var(--text-muted)'} />
                  <span className="session-title">{s.title}</span>
                </div>
                <button 
                  className="session-delete-btn" 
                  onClick={(e) => handleDeleteSession(e, s.session_id)}
                  title="删除此分析会话"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))
          )}
        </div>

        {/* 侧边栏底部隔离用户信息 */}
        <div className="sidebar-user">
          <div className="user-badge-group">
            <div className="user-badge">
              <User size={14} color="var(--color-primary)" />
              <span style={{ fontWeight: 600 }}>{username}</span>
            </div>
            <div className="tenant-id-badge" title={activeThreadId}>
              会话: {activeThreadId.substring(0, 18)}...
            </div>
          </div>
          <button className="logout-btn" onClick={handleLogout} title="登出控制台">
            <LogOut size={15} />
          </button>
        </div>
      </div>

      {/* 2. 右侧主工作区 */}
      <div className="main-workspace">
        
        {/* 数据隔离源卡片 */}
        <div className="glass-card kb-section">
          <div className="kb-header">
            <h3>
              <FileSpreadsheet size={17} color="var(--color-primary)" /> 专属数据源隔离沙箱
            </h3>
            <div className="kb-actions">
              {activeFilePath && (
                <span className="file-active-badge">
                  当前载入: {activeFilePath.split('/').pop().split('\\').pop()}
                </span>
              )}
            </div>
          </div>

          <div 
            className={`upload-dropzone ${isDragging ? 'dragging' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => document.getElementById('file-input').click()}
          >
            <input 
              type="file" 
              id="file-input" 
              style={{ display: 'none' }} 
              onChange={(e) => handleUploadFile(e.target.files[0])}
            />
            <UploadCloud size={30} className="upload-icon" />
            <p>点击或拖放 CSV / Excel 数据源到这里</p>
            <span>自动在物理磁盘上按用户 ID 进行隔离存储 (防信息泄露)</span>

            {isUploading && (
              <div className="upload-progress-overlay">
                <div className="progress-spinner"></div>
                <div className="progress-text">{uploadProgress}</div>
              </div>
            )}
          </div>
        </div>

        {/* 聊天问答区 */}
        <div className="chat-container">
          <div className="chat-messages">
            {messages.length === 0 ? (
              <div className="empty-chat-state">
                <FileSpreadsheet size={42} color="rgba(255,127,14,0.04)" />
                <h2>数据可视化分析智能体</h2>
                <p>上传隔离数据源文件后，请输入您的绘图与分析请求。</p>
                <div className="feature-grid">
                  <div className="feature-item">
                    <strong>🔍 字段智能探针</strong>
                    <span>分析前自动梳理特征与缺失值</span>
                  </div>
                  <div className="feature-item">
                    <strong>💻 动态沙箱执行</strong>
                    <span>生成并运行 Python 代码进行绘图</span>
                  </div>
                  <div className="feature-item">
                    <strong>🙋 人在回路联动</strong>
                    <span>在关键点挂起并等候您纠偏</span>
                  </div>
                </div>
              </div>
            ) : (
              messages.map((msg, idx) => {
                const isAssistant = msg.role === 'assistant';
                const hasReport = isAssistant && msg.content.includes('🔍 **【数据探针检测报告】**');
                let displayContent = msg.content;
                let reportContent = '';

                if (hasReport) {
                  // 分割检测报告
                  const parts = msg.content.split('🔍 **【数据探针检测报告】**');
                  displayContent = parts[0];
                  reportContent = parts[1];
                }

                return (
                  <div key={idx} className={`message-row ${msg.role}`}>
                    <div className="message-meta">
                      {msg.role === 'user' ? '您' : 'DataViz 分析引擎'}
                      {isAssistant && currentStatus && idx === messages.length - 1 && (
                        <span className="live-status-pill">
                          <Loader size={11} className="spin-icon" />
                          {currentStatus}
                        </span>
                      )}
                    </div>

                    <div className={`chat-bubble ${msg.role}`}>
                      {/* 渲染数据探针折叠报告 */}
                      {reportContent && (
                        <div className="profiler-card">
                          <div className="profiler-card-header">
                            <Activity size={14} color="var(--color-primary)" />
                            <span>🔍 数据结构特征探针分析报告 (点击展开)</span>
                          </div>
                          <details className="profiler-details">
                            <summary>查看详细数据拓扑特征</summary>
                            <div className="profiler-body" style={{ whiteSpace: 'pre-wrap' }}>
                              {reportContent.trim()}
                            </div>
                          </details>
                        </div>
                      )}

                      {/* 渲染正文（正则替换后的 Markdown 本地图片路径） */}
                      <div className="markdown-render" style={{ whiteSpace: 'pre-wrap' }}>
                        {parseLocalImagePath(displayContent) || (isSending && idx === messages.length - 1 ? '正在探针识别中...' : '')}
                      </div>

                      {/* ⚡ 脉冲执行链路追踪日志 (Trace Logs Timeline) */}
                      {isAssistant && msg.trace_logs && msg.trace_logs.length > 0 && (
                        <div className="trace-timeline-container">
                          <div className="trace-timeline-header">
                            <Activity size={12} />
                            <span>Agent 物理沙箱执行状态链路</span>
                          </div>
                          
                          <div className="trace-pulse-list">
                            {msg.trace_logs.map((log, lIdx) => {
                              const isEnd = log.status === 'end';
                              const isError = log.status === 'error';
                              
                              return (
                                <div key={lIdx} className={`trace-pulse-item ${log.status}`}>
                                  <div className="pulse-dot"></div>
                                  <div className="pulse-content">
                                    <span className="node-badge">{log.node}</span>
                                    <span className="message">{log.message}</span>
                                    {log.duration !== undefined && (
                                      <span className="duration-tag">{log.duration}s</span>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 人在回路 (HITL) 审批拦截提示 */}
          {isHitlSuspended && (
            <div className="hitl-alert-overlay">
              <div className="hitl-alert-card">
                <div className="card-header">
                  <AlertTriangle size={18} color="var(--color-danger)" />
                  <h4>⚠️ 人在回路 (HITL) 决策反馈中</h4>
                </div>
                <p>
                  沙箱检测到上传的列数据存在语义缺失或字段歧义，系统自动在 <code>human_node</code> 中断挂起。
                  请在下方输入您的纠偏指令（例如：“使用'日期'列作为X轴，缺失值采用均值填充”），发送后 Agent 将被唤醒并重新分析。
                </p>
              </div>
            </div>
          )}

          {/* 底部输入框 */}
          <form onSubmit={handleSendMessage} className="chat-input-bar">
            <input 
              type="text" 
              className="neon-input" 
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder={isHitlSuspended ? "⚠️ 请输入您的决策纠偏指令..." : "请输入分析绘图指令 (例如: 帮我绘制销售额与利润的散点图)..."}
              disabled={isSending && !isHitlSuspended}
            />
            <button type="submit" className="neon-btn" disabled={isSending && !isHitlSuspended}>
              <Send size={14} /> {isHitlSuspended ? '决策纠错' : '分析'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default App;
