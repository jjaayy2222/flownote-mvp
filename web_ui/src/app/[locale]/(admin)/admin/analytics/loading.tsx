import { Loader2 } from 'lucide-react';

export default function AnalyticsLoading() {
  return (
    <div className="flex h-[50vh] flex-col items-center justify-center space-y-4">
      <Loader2 className="h-10 w-10 animate-spin text-blue-600 dark:text-blue-500" />
      <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
        Loading analytics charts...
      </p>
    </div>
  );
}
