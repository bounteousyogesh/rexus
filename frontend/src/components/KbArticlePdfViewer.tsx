import { useMemo, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import type { KbArticle } from '../types';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

function decodePdf(pdfBase64: string): Uint8Array | null {
  try {
    return Uint8Array.from(atob(pdfBase64), (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
}

export function KbArticlePdfViewer({ article }: { article: KbArticle }) {
  const pdfBase64 = article.pdf_base64;
  const title = `${article.number} PDF`;

  const file = useMemo(() => {
    if (!pdfBase64) return null;
    const data = decodePdf(pdfBase64);
    return data ? { data } : null;
  }, [pdfBase64]);

  const [numPages, setNumPages] = useState(0);

  if (!file) {
    return <p className="text-sm text-slate-400 italic py-2">PDF preview unavailable.</p>;
  }

  return (
    <div
      className="max-h-[min(70vh,720px)] overflow-y-auto border border-amber-100 rounded-md bg-slate-50"
      aria-label={title}
    >
      <Document
        file={file}
        onLoadSuccess={({ numPages: n }) => setNumPages(n)}
        loading={<p className="text-sm text-slate-500 py-4 px-3">Loading PDF…</p>}
        error={<p className="text-sm text-slate-400 italic py-2 px-3">PDF preview unavailable.</p>}
      >
        {Array.from({ length: numPages }, (_, i) => (
          <Page key={i + 1} pageNumber={i + 1} width={720} className="mx-auto" />
        ))}
      </Document>
    </div>
  );
}
