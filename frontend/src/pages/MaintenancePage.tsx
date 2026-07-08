import { Wrench, ExternalLink } from 'lucide-react';

export type MaintenanceJobId = 'sn-sync' | 'kb-mapping-refresh' | 'new-incidents-sync' | 'rexus-db-sync';

interface MaintenancePageProps {
  onOpenJob: (id: MaintenanceJobId) => void;
}

const JOBS: { id: MaintenanceJobId; title: string; description: string }[] = [
  {
    id: 'sn-sync',
    title: 'ServiceNow Sync',
    description: 'Import closed incidents from ServiceNow by date range (manual historical import).',
  },
  {
    id: 'kb-mapping-refresh',
    title: 'Refresh Knowledge Article Mapping',
    description: 'Sync knowledge article links from ServiceNow for incidents in the database.',
  },
  {
    id: 'new-incidents-sync',
    title: "Sync & Analyze Today's New Incidents",
    description: 'Sync new incidents, run REXUS analysis, and post analysis links as ServiceNow comments.',
  },
  {
    id: 'rexus-db-sync',
    title: 'REXUS DB Sync',
    description: 'Automated scheduled sync of closed-incident updates from ServiceNow into the knowledge base.',
  },
];

export default function MaintenancePage({ onOpenJob }: MaintenancePageProps) {
  return (
    <div className="p-6 space-y-4 max-w-[1000px]">
      <div>
        <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
          <Wrench size={22} /> Maintenance
        </h2>
        <p className="text-sm text-slate-500">Operational tasks for keeping the knowledge base up to date</p>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Title</th>
              <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider w-32">Action</th>
            </tr>
          </thead>
          <tbody>
            {JOBS.map((job) => (
              <tr key={job.id} className="border-b border-slate-50 last:border-0">
                <td className="px-4 py-4">
                  <p className="font-medium text-slate-800">{job.title}</p>
                  <p className="text-xs text-slate-500 mt-1">{job.description}</p>
                </td>
                <td className="px-4 py-4 text-right">
                  <button
                    onClick={() => onOpenJob(job.id)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 text-white rounded-lg text-xs font-medium hover:bg-slate-800 transition-colors"
                  >
                    <ExternalLink size={12} /> Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
