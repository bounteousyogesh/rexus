import { useState, useRef, useEffect } from 'react';
import { BASE } from '../api';
import { KbArticlePdfViewer } from '../components/KbArticlePdfViewer';
import { Zap, Loader2, Upload, ChevronDown, BookOpen, AlertCircle, Copy, Check, Mic, MicOff, Send, MessageSquare, Search } from 'lucide-react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api, type AnalyzeResult, type KbArticle } from '../api';

type Step = 'idle' | 'fetching' | 'parsing' | 'embedding' | 'searching' | 'playbooks' | 'done';

const STEPS: { key: Step; label: string }[] = [
  { key: 'fetching', label: 'Fetching from ServiceNow' },
  { key: 'parsing', label: 'Parsing ticket data' },
  { key: 'embedding', label: 'Generating embedding' },
  { key: 'searching', label: 'Vector similarity search' },
  { key: 'playbooks', label: 'Generating playbook' },
  { key: 'done', label: 'Analysis complete' },
];

export default function AnalyzePage() {
  // ENH-012: All useState declarations at top of component, before any function definitions
  const [incNumber, setIncNumber] = useState('');
  const [incFetched, setIncFetched] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [ticketJson, setTicketJson] = useState('');
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [step, setStep] = useState<Step>('idle');
  const [expandedInc, setExpandedInc] = useState<string | null>(null);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const [isDev, setIsDev] = useState(true);

  // Check environment — hide PDF upload in production
  useEffect(() => {
    fetch(`${BASE}/config/llm`).then(r => r.json()).then(d => {
      setIsDev(d.environment !== 'production');
    }).catch(() => {});
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError('');
    if (!file.name.endsWith('.pdf')) { setError('Please upload a PDF file'); return; }

    setStep('parsing');
    try {
      const parsed = await api.parsePdf(file);
      setTicketJson(JSON.stringify(parsed, null, 2));
      setIncFetched(true);
      setIncNumber('');
      setStep('idle');
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`PDF parsing failed: ${message}`);
      setStep('idle');
    }
    if (fileRef.current) fileRef.current.value = '';
  };

  const handleAnalyze = async () => {
    setError('');

    // If we already have JSON (from PDF or prior fetch), go straight to analysis
    if (incFetched && ticketJson) {
      try {
        setStep('parsing');
        setResult(null);
        setExpandedInc(null);
        const parsed = JSON.parse(ticketJson);

        setStep('playbooks');
        const data = await api.analyze(parsed);
        setStep('done');
        setResult(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        setStep('idle');
      }
      return;
    }

    // Otherwise, fetch from ServiceNow first
    const trimmed = incNumber.trim().toUpperCase();
    if (!trimmed) { setError('Enter an incident number'); return; }
    if (!/^INC\d+$/.test(trimmed)) { setError('Invalid format. Enter an INC number (e.g. INC0000000)'); return; }

    setStep('fetching');
    setFetching(true);
    setResult(null);
    setExpandedInc(null);
    try {
      const fetched = await api.fetchIncident(trimmed);
      setTicketJson(JSON.stringify(fetched, null, 2));
      setIncFetched(true);
      setStep('idle');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('404')) {
        setError(`Incident ${trimmed} was not found in the configured ServiceNow instance.`);
      } else if (msg.includes('503')) {
        setError('ServiceNow credentials are not configured. Contact your administrator.');
      } else {
        setError(`Failed to fetch from ServiceNow: ${msg}`);
      }
      setStep('idle');
    } finally {
      setFetching(false);
    }
  };

  const confidenceColor = (score: number) =>
    score >= 0.7 ? 'text-emerald-600' : score >= 0.5 ? 'text-amber-600' : 'text-red-500';
  const confidenceBg = (score: number) =>
    score >= 0.7 ? 'bg-emerald-500' : score >= 0.5 ? 'bg-amber-500' : 'bg-red-500';

  return (
    <div className="p-6 space-y-5 max-w-[1200px]">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Ticket Analysis</h2>
        <p className="text-sm text-slate-500">Enter a ServiceNow incident number{isDev ? ' or upload a PDF' : ''} to run AI analysis</p>
      </div>

      <div className="grid grid-cols-[1fr_320px] gap-5">
        {/* Left: Input */}
        <div className="space-y-4">
          {/* INC Number input */}
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">ServiceNow Incident Number</label>
            <div className="flex gap-3">
              <input
                value={incNumber}
                onChange={(e) => { setIncNumber(e.target.value.toUpperCase()); setIncFetched(false); setTicketJson(''); setResult(null); setError(''); }}
                onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                placeholder="INC0000000"
                className="flex-1 px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg text-lg font-mono tracking-wider focus:outline-none focus:ring-2 focus:ring-blue-500"
                maxLength={15}
                disabled={fetching}
              />
              <button
                onClick={handleAnalyze}
                disabled={fetching || (step !== 'idle' && step !== 'done')}
                className="flex items-center gap-2 px-6 py-3 bg-slate-900 text-white rounded-lg text-sm font-semibold hover:bg-slate-800 disabled:opacity-40 transition-colors"
              >
                {fetching ? <Loader2 size={16} className="animate-spin" /> : step !== 'idle' && step !== 'done' ? <Loader2 size={16} className="animate-spin" /> : !incFetched ? <Search size={16} /> : <Zap size={16} />}
                {fetching ? 'Fetching...' : step !== 'idle' && step !== 'done' ? 'Analyzing...' : !incFetched ? 'Fetch' : 'Analyze'}
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              {!incFetched
                ? "We'll fetch all details directly from ServiceNow."
                : "Details fetched. Review below, then click Analyze."}
            </p>
          </div>

          {/* OR: Upload PDF — only shown in development */}
          {isDev && (
            <div
              className="bg-white rounded-xl border-2 border-dashed border-slate-200 hover:border-blue-300 transition-colors p-4 text-center cursor-pointer"
              onClick={() => fileRef.current?.click()}
            >
              <Upload size={20} className="mx-auto text-slate-400 mb-1" />
              <p className="text-sm font-medium text-slate-600">Or upload a ServiceNow PDF</p>
              <p className="text-xs text-slate-400 mt-0.5">Click to browse</p>
              <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={handleFileUpload} />
            </div>
          )}

          {/* Fetched/parsed JSON preview */}
          {incFetched && ticketJson && (
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1">Fetched from ServiceNow:</p>
              <textarea
                value={ticketJson}
                readOnly
                className="w-full h-48 p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs font-mono resize-none"
              />
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
              <AlertCircle size={16} /> {error}
            </div>
          )}

        </div>

        {/* Right: Progress + Feedback */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-slate-100 p-5">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Analysis Progress</h3>
            <div className="space-y-3">
              {STEPS.map((s) => {
                const stepIdx = STEPS.findIndex(x => x.key === step);
                const thisIdx = STEPS.findIndex(x => x.key === s.key);
                const isActive = s.key === step;
                const isDone = stepIdx > thisIdx || step === 'done';
                return (
                  <div key={s.key} className="flex items-center gap-3">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                      isDone ? 'bg-emerald-500 text-white' :
                      isActive ? 'bg-blue-500 text-white animate-pulse' :
                      'bg-slate-100 text-slate-400'
                    }`}>
                      {isDone ? '✓' : thisIdx + 1}
                    </div>
                    <span className={`text-sm ${isDone ? 'text-slate-700' : isActive ? 'text-blue-700 font-medium' : 'text-slate-400'}`}>{s.label}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Feedback box */}
          {result && (
            <FeedbackBox analysisId={result.analysis_id} incidentNumber={result.incident_number} />
          )}
        </div>
      </div>

      {/* ═══ RESULTS — compact layout ═══ */}
      {result && (
        <div className="space-y-3">
          {/* Row 1: Confidence + Cluster + Problem Tag */}
          <div className="grid grid-cols-[auto_1fr_auto] gap-3 items-stretch">
            {/* Confidence */}
            <div className="bg-white rounded-lg p-3 shadow-sm border border-slate-100 flex items-center gap-3">              
	    <p className={`text-2xl font-bold ${confidenceColor(result.confidence_score)}`}>
                {(Math.min(result.confidence_score, 1) * 100).toFixed(0)}%
              </p>
              <div>
                <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className={`h-2 rounded-full ${confidenceBg(result.confidence_score)}`} style={{ width: `${Math.min(result.confidence_score, 1) * 100}%` }} />
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">{result.match_count} matches</p>
              </div>
            </div>

            {/* Cluster */}
            {result.dominant_cluster && (
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
                <p className="text-[10px] text-blue-600 uppercase tracking-wider font-semibold">Matched Group</p>
                <p className="text-sm font-bold text-blue-900">{result.dominant_cluster.cluster_name}</p>
                <p className="text-[10px] text-blue-600">{result.dominant_cluster.incident_count} incidents | {result.dominant_cluster.dominant_category}</p>
              </div>
            )}

            {/* Problem Tag */}
            {result.focused_playbook?.top_problem && (
              <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                <p className="text-[10px] text-purple-600 uppercase tracking-wider font-semibold">Suggested Problem</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="font-mono text-sm font-bold text-purple-900">{result.focused_playbook.top_problem.id}</span>
                  <CopyButton text={result.focused_playbook.top_problem.id} label="" />
                </div>
                <p className="text-[10px] text-purple-600">{result.focused_playbook.top_problem.count} similar incidents</p>
                {result.focused_playbook.secondary_problem && (
                  <p className="text-[10px] text-purple-500 mt-0.5">Alt: {result.focused_playbook.secondary_problem.id}</p>
                )}
              </div>
            )}
          </div>

          {/* Row 1b: Knowledge Article from similar incidents (URL + PDF when available) */}
          <KnowledgeArticlesSection
            articles={result.focused_playbook?.kb_articles || []}
          />

          {/* Row 2: Playbook (KB summary when linked, else similar-incident LLM) */}
          {result.focused_playbook?.playbook && (
            <CollapsiblePlaybook
              title={
                hasKbArticleNumber(result.focused_playbook.kb_articles)
                  ? 'Playbook (Knowledge Article)'
                  : 'Playbook'
              }
              content={result.focused_playbook.playbook}
              grounding={result.focused_playbook.grounding_score}
              sourceCount={result.focused_playbook.source_incident_count}
              totalSimilar={result.focused_playbook.total_similar}
              sourceDetail={
                hasKbArticleNumber(result.focused_playbook.kb_articles)
                  ? [
                      result.focused_playbook.kb_articles?.[0]?.number,
                      result.focused_playbook.kb_source_incident
                        ? `via ${result.focused_playbook.kb_source_incident}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')
                  : undefined
              }
              defaultOpen={!hasKbArticleNumber(result.focused_playbook.kb_articles)}
            />
          )}

          {/* Row 3: Similar Incidents (compact table, collapsed) */}
          <details className="bg-white rounded-lg shadow-sm border border-slate-100 overflow-hidden">
            <summary className="p-3 cursor-pointer text-xs font-semibold text-slate-600 hover:bg-slate-50">
              Similar Incidents ({result.similar_incidents.length})
            </summary>
            <div className="max-h-60 overflow-y-auto">
              <table className="w-full text-[11px]">
                <thead className="bg-slate-50 sticky top-0">
                  <tr className="text-left text-slate-500">
                    <th className="px-2 py-1.5">INC#</th>
                    <th className="px-2 py-1.5">Description</th>
                    <th className="px-2 py-1.5">System</th>
                    <th className="px-2 py-1.5 text-right">Sim%</th>
                  </tr>
                </thead>
                <tbody>
                  {result.similar_incidents.map((inc) => (
                    <tr key={inc.incident_number} className="border-t border-slate-50 hover:bg-slate-50 cursor-pointer"
                      onClick={() => setExpandedInc(expandedInc === inc.incident_number ? null : inc.incident_number)}>
                      <td className="px-2 py-1 font-mono text-blue-600">{inc.incident_number}</td>
                      <td className="px-2 py-1 text-slate-700 truncate max-w-xs">{inc.short_description}</td>
                      <td className="px-2 py-1 text-slate-500">{inc.cmdb_ci}</td>                      
		      <td className={`px-2 py-1 text-right font-semibold ${confidenceColor(inc.similarity_score || 0)}`}>
                        {(Math.min(inc.similarity_score || 0, 1) * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

function FeedbackBox({ analysisId, incidentNumber }: { analysisId?: number; incidentNumber?: string }) {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setTranscribing(true);
        try {
          const transcribed = await api.transcribeAudio(blob);
          setText(prev => prev ? `${prev} ${transcribed}` : transcribed);
        } catch {
          setText(prev => prev + ' [transcription failed]');
        } finally {
          setTranscribing(false);
        }
      };

      mediaRecorder.start();
      setRecording(true);
    } catch {
      alert('Microphone access denied');
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  const handleSubmit = async () => {
    if (!text.trim()) return;
    setSubmitting(true);
    try {
      await api.submitFeedback({
        analysis_id: analysisId,
        incident_number: incidentNumber,
        feedback_text: text.trim(),
        feedback_type: 'general',
        input_method: recording ? 'voice' : 'text',
      });
      setSubmitted(true);
      setTimeout(() => setSubmitted(false), 3000);
      setText('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-100 p-4">
      <div className="flex items-center gap-2 mb-3">
        <MessageSquare size={14} className="text-slate-500" />
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Feedback</h3>
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Was this analysis helpful? Any issues with the suggestions?"
        className="w-full h-20 p-2.5 border border-slate-200 rounded-lg text-xs resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <div className="flex items-center justify-between mt-2">
        <button
          onClick={recording ? stopRecording : startRecording}
          disabled={transcribing}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            recording
              ? 'bg-red-500 text-white animate-pulse'
              : transcribing
                ? 'bg-slate-100 text-slate-400'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
          }`}
        >
          {recording ? <MicOff size={12} /> : transcribing ? <Loader2 size={12} className="animate-spin" /> : <Mic size={12} />}
          {recording ? 'Stop' : transcribing ? 'Transcribing...' : 'Voice'}
        </button>
        <button
          onClick={handleSubmit}
          disabled={!text.trim() || submitting}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500 text-white rounded-lg text-xs font-medium hover:bg-blue-600 disabled:opacity-40 transition-colors"
        >
          {submitted ? <Check size={12} /> : submitting ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
          {submitted ? 'Sent!' : 'Send'}
        </button>
      </div>
    </div>
  );
}

function hasKbArticleNumber(kbArticles?: KbArticle[]): boolean {
  return Boolean(kbArticles?.some((a) => a.number?.trim()));
}

function KnowledgeArticlesSection({ articles }: { articles: KbArticle[] }) {
  const has = articles.length > 0;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-amber-200 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 bg-amber-50 border-b border-amber-100">
        <div className="flex items-center gap-2">
          <BookOpen size={16} className="text-amber-700" />
          <h3 className="text-sm font-semibold text-amber-900">Knowledge Article</h3>
          {has && (
            <span className="text-xs px-2 py-0.5 bg-amber-200 text-amber-900 rounded-full font-medium">
              from similar incident
            </span>
          )}
        </div>
      </div>
      <div className="px-4 py-3">
        {!has ? (
          <p className="text-sm text-slate-400 italic">
            N/A — no knowledge article linked to a similar incident.
          </p>
        ) : (
          <div className="space-y-6">
            {articles.map((ka) => {
              const hasNumber = Boolean(ka.number?.trim());
              const showPdfViewer = Boolean(ka.pdf_base64);

              return (
                <article key={ka.sys_id || ka.number} className="space-y-3">
                  <div className="flex items-start gap-3 flex-wrap">
                    <span className="font-mono text-xs text-amber-700 shrink-0 pt-0.5">{ka.number}</span>
                    {ka.match_percent != null && (
                      <span className="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-800 rounded font-semibold shrink-0">
                        {ka.match_percent.toFixed(0)}% match
                        {ka.matched_via_incident ? ` (${ka.matched_via_incident})` : ''}
                      </span>
                    )}
                    {ka.url ? (
                      <a
                        href={ka.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-blue-600 hover:text-blue-800 hover:underline flex-1"
                      >
                        {ka.short_description || ka.kb_title || ka.number}
                      </a>
                    ) : (
                      <span className="text-sm text-slate-700 flex-1">
                        {ka.short_description || ka.kb_title || ka.number}
                      </span>
                    )}
                    {ka.kb_category_display && (
                      <span className="text-[10px] text-slate-500 shrink-0">{ka.kb_category_display}</span>
                    )}
                  </div>
                  {hasNumber && (
                    showPdfViewer ? (
                      <KbArticlePdfViewer article={ka} />
                    ) : (
                      <p className="text-sm text-slate-400 italic">
                        PDF preview unavailable — open the article link above or check ServiceNow / local KB storage.
                      </p>
                    )
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function CollapsiblePlaybook({ title, content, grounding, sourceCount, totalSimilar, sourceDetail, defaultOpen }: {
  title: string;
  content: string;
  grounding: number;
  sourceCount: number;
  totalSimilar: number;
  /** When set (e.g. KB number), shown instead of incident count subtitle. */
  sourceDetail?: string;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-white rounded-xl shadow-sm border border-emerald-200 overflow-hidden">
      <div
        className="flex items-center justify-between p-4 border-b border-emerald-100 bg-emerald-50 cursor-pointer"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-2">
          <BookOpen size={18} className="text-emerald-600" />
          <h3 className="text-sm font-semibold text-emerald-800">{title}</h3>
          <span className="text-xs px-2 py-0.5 bg-emerald-200 text-emerald-800 rounded-full font-medium">
            {(grounding * 100).toFixed(0)}% grounded
          </span>
          <span className="text-xs text-emerald-600">
            {sourceDetail ?? `${sourceCount} of ${totalSimilar} incidents`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <CopyButton text={content} label="Copy" />
          <ChevronDown size={16} className={`text-emerald-600 transition-transform ${open ? 'rotate-180' : ''}`} />
        </div>
      </div>
      {open && (
        <div className="p-6 overflow-y-auto" style={{ maxHeight: '70vh' }}>
          <Markdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({children}) => <h1 className="text-xl font-bold text-slate-900 mb-4 pb-2 border-b border-slate-200">{children}</h1>,
              h2: ({children}) => <h2 className="text-base font-bold text-slate-800 mt-6 mb-3 pb-1 border-b border-slate-100">{children}</h2>,
              h3: ({children}) => <h3 className="text-sm font-semibold text-slate-700 mt-4 mb-2">{children}</h3>,
              p: ({children}) => <p className="text-sm text-slate-700 mb-2 leading-relaxed">{children}</p>,
              ul: ({children}) => <ul className="text-sm text-slate-700 mb-3 space-y-1 ml-4 list-disc">{children}</ul>,
              ol: ({children}) => <ol className="text-sm text-slate-700 mb-3 space-y-1 ml-4 list-decimal">{children}</ol>,
              li: ({children}) => <li className="text-sm text-slate-700 leading-relaxed">{children}</li>,
              strong: ({children}) => <strong className="font-semibold text-slate-900">{children}</strong>,
              table: ({children}) => (
                <div className="overflow-x-auto my-3 border border-slate-200 rounded-lg">
                  <table className="w-full text-xs">{children}</table>
                </div>
              ),
              thead: ({children}) => <thead className="bg-slate-50 border-b border-slate-200">{children}</thead>,
              th: ({children}) => <th className="px-3 py-2 text-left font-semibold text-slate-600 whitespace-nowrap">{children}</th>,
              td: ({children}) => <td className="px-3 py-1.5 text-slate-700 border-t border-slate-100">{children}</td>,
              code: ({children, className}) => {
                if (className) return <code className="block bg-slate-50 p-3 rounded text-xs font-mono overflow-x-auto">{children}</code>;
                return <code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono text-slate-800">{children}</code>;
              },
              hr: () => <hr className="my-4 border-slate-200" />,
            }}
          >
            {content}
          </Markdown>
        </div>
      )}
    </div>
  );
}



function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors bg-white border-slate-200 hover:bg-slate-50 text-slate-600"
    >
      {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
      {copied ? 'Copied!' : label || 'Copy'}
    </button>
  );
}
