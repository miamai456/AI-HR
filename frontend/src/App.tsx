import {
  Activity,
  BarChart3,
  BookOpen,
  Bot,
  Check,
  ChevronRight,
  CircleAlert,
  Database,
  ExternalLink,
  FileSearch,
  Gauge,
  LoaderCircle,
  Send,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";

import { applyAssistantEvent, initialAssistantRun } from "./assistant-state";
import {
  type DocumentSearchResult,
  getAnalysisContext,
  searchDocuments,
  streamAssistant,
} from "./api";

type StepStatus = "pending" | "running" | "complete" | "error";

const examples = [
  "最近招聘漏斗的主要流失点在哪里？",
  "AI推荐与人工推荐的面试率差异是否可信？",
  "当前数据质量风险会影响哪些结论？",
];

function extractMetrics(context: Record<string, unknown>) {
  const overview = context.overview as Record<string, unknown> | undefined;
  const summary = overview?.summary as Record<string, unknown> | undefined;
  return [
    { label: "推荐量", value: String(summary?.recommended ?? "--") },
    { label: "面试率", value: asPercent(summary?.interview_rate) },
    { label: "入职率", value: asPercent(summary?.hire_rate) },
  ];
}

function asPercent(value: unknown) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "--";
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === "running") return <LoaderCircle className="spin" size={15} />;
  if (status === "complete") return <Check size={15} />;
  if (status === "error") return <CircleAlert size={15} />;
  return <ChevronRight size={15} />;
}

export default function App() {
  const [question, setQuestion] = useState("");
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const [context, setContext] = useState<Record<string, unknown>>({});
  const [contextStatus, setContextStatus] = useState<StepStatus>("running");
  const [searchStatus, setSearchStatus] = useState<StepStatus>("pending");
  const [assistant, setAssistant] = useState(initialAssistantRun);
  const [sources, setSources] = useState<DocumentSearchResult[]>([]);

  useEffect(() => {
    getAnalysisContext()
      .then((payload) => {
        setContext(payload);
        setContextStatus("complete");
      })
      .catch(() => setContextStatus("error"));
  }, []);

  const metrics = useMemo(() => extractMetrics(context), [context]);
  const isRunning = assistant.status === "streaming";

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isRunning) return;
    setSubmittedQuestion(trimmed);
    setAssistant({ ...initialAssistantRun(), status: "streaming" });
    setSearchStatus("running");
    setSources([]);

    const sourceTask = searchDocuments(trimmed)
      .then((results) => {
        setSources(results);
        setSearchStatus("complete");
      })
      .catch(() => setSearchStatus("error"));

    try {
      await streamAssistant(trimmed, context, (sseEvent) => {
        setAssistant((current) => applyAssistantEvent(current, sseEvent));
      });
    } catch (error) {
      setAssistant((current) => ({
        ...current,
        status: "error",
        error: error instanceof Error ? error.message : "Assistant request failed",
      }));
    }
    await sourceTask;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span>AI</span>HR</div>
        <nav aria-label="主导航">
          <a href="http://localhost:8501" target="_blank" rel="noreferrer"><Gauge size={18} />经营概览</a>
          <a href="http://localhost:8501" target="_blank" rel="noreferrer"><Users size={18} />招聘漏斗</a>
          <a href="http://localhost:8501" target="_blank" rel="noreferrer"><BarChart3 size={18} />效果评估</a>
          <a href="http://localhost:8501" target="_blank" rel="noreferrer"><Activity size={18} />模型监控</a>
          <a className="active" href="/"><Bot size={18} />AI分析助手</a>
        </nav>
        <div className="sidebar-footer">
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
            <Database size={16} />API文档<ExternalLink size={13} />
          </a>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <p className="eyebrow">ANALYSIS WORKBENCH</p>
            <h1>AI 分析助手</h1>
          </div>
          <div className={`service-status ${contextStatus}`}>
            <span />{contextStatus === "complete" ? "数据已就绪" : contextStatus === "error" ? "数据连接异常" : "正在加载"}
          </div>
        </header>

        <section className="metric-strip" aria-label="当前指标快照">
          {metrics.map((metric) => (
            <div key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong></div>
          ))}
          <div><span>分析口径</span><strong>成熟队列</strong></div>
        </section>

        <div className="workspace">
          <section className="conversation" aria-live="polite">
            {!submittedQuestion && (
              <div className="empty-state">
                <div className="assistant-mark"><Sparkles size={22} /></div>
                <h2>经营与招聘数据分析</h2>
                <div className="example-list">
                  {examples.map((example) => (
                    <button key={example} type="button" onClick={() => setQuestion(example)}>
                      {example}<ChevronRight size={16} />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {submittedQuestion && (
              <div className="thread">
                <div className="user-message"><span>你</span><p>{submittedQuestion}</p></div>
                <article className="assistant-message">
                  <div className="message-label"><Bot size={17} />AIHR</div>
                  {assistant.content ? <ReactMarkdown>{assistant.content}</ReactMarkdown> : isRunning ? (
                    <div className="thinking"><LoaderCircle className="spin" size={18} />正在分析结构化指标与知识库</div>
                  ) : null}
                  {assistant.status === "error" && (
                    <div className="error-banner"><CircleAlert size={17} />{assistant.error}</div>
                  )}
                </article>
              </div>
            )}

            <form className="composer" onSubmit={submit}>
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="输入分析问题"
                rows={3}
                maxLength={2000}
              />
              <div className="composer-actions">
                <span>{question.length}/2000</span>
                <button type="submit" disabled={!question.trim() || isRunning} title="发送分析请求" aria-label="发送分析请求">
                  {isRunning ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}
                </button>
              </div>
            </form>
          </section>

          <aside className="evidence-panel">
            <section>
              <h2><ShieldCheck size={17} />可信度</h2>
              <dl>
                <div><dt>等级</dt><dd>{String(assistant.trust.confidence ?? "待评估")}</dd></div>
                <div><dt>模型</dt><dd>{assistant.model || "待调用"}</dd></div>
                <div><dt>数据质量</dt><dd>{String(assistant.trust.data_quality_status ?? "待检查")}</dd></div>
              </dl>
            </section>

            <section>
              <h2><FileSearch size={17} />执行链</h2>
              <ol className="run-steps">
                <li className={contextStatus}><StepIcon status={contextStatus} /><span>加载分析上下文<small>inspect_metrics</small></span></li>
                <li className={searchStatus}><StepIcon status={searchStatus} /><span>检索知识文档<small>search_docs</small></span></li>
                <li className={assistant.status === "idle" ? "pending" : assistant.status === "streaming" ? "running" : assistant.status === "complete" ? "complete" : "error"}>
                  <StepIcon status={assistant.status === "idle" ? "pending" : assistant.status === "streaming" ? "running" : assistant.status === "complete" ? "complete" : "error"} />
                  <span>生成可信回答<small>assistant_stream</small></span>
                </li>
              </ol>
            </section>

            <section>
              <h2><BookOpen size={17} />引用来源</h2>
              <div className="source-list">
                {sources.length === 0 ? <p className="muted">暂无检索结果</p> : sources.map((source) => (
                  <div className="source" key={source.document.document_id}>
                    <span>{source.document.document_type}</span>
                    <strong>{source.document.title}</strong>
                    <p>{source.document.source_id}</p>
                  </div>
                ))}
              </div>
            </section>
          </aside>
        </div>
      </main>
    </div>
  );
}
