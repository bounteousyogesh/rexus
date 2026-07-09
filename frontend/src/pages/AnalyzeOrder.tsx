import OrderAnalyzePanel from '../components/OrderAnalyzePanel';

export default function AnalyzeOrderPage() {
  return (
    <div className="p-6 space-y-5 max-w-[1200px]">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Order Number Analysis</h2>
        <p className="text-sm text-slate-500">
          Enter a sales order number to retrieve related incidents from the local database
        </p>
      </div>
      <OrderAnalyzePanel />
    </div>
  );
}
