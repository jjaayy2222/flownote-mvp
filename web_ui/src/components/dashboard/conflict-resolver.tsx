// web_ui/src/components/dashboard/conflict-resolver.tsx

"use client"

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"

interface ConflictResolverProps {
  isOpen: boolean;
  onClose: () => void;
  conflict: {
    id: string;
    path: string;
    localContent: string;
    remoteContent: string;
  } | null;
  onResolve: (decision: 'local' | 'remote' | 'both') => void;
}

export function ConflictResolver({ 
  isOpen, onClose, conflict, onResolve 
}: ConflictResolverProps) {
  if (!conflict) return null;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Resolve Conflict: {conflict.path}</DialogTitle>
          <DialogDescription>
            Choose which version of the file to preserve.
          </DialogDescription>
        </DialogHeader>
        
        <div className="grid grid-cols-2 gap-4 flex-1 min-h-0 py-4">
          {/* Local Column */}
          <div className="flex flex-col h-full border rounded-lg overflow-hidden">
            <div className="bg-blue-50 p-3 border-b flex justify-between items-center">
              <span className="font-semibold text-blue-700">Local Version (Current)</span>
            </div>
            <ScrollArea className="flex-1 bg-white p-4">
              <pre className="text-xs font-mono whitespace-pre-wrap">{conflict.localContent}</pre>
            </ScrollArea>
            <div className="p-3 bg-gray-50 border-t">
              <Button className="w-full bg-blue-600 hover:bg-blue-700" onClick={() => onResolve('local')}>
                Keep Local
              </Button>
            </div>
          </div>
          
          {/* Remote Column */}
          <div className="flex flex-col h-full border rounded-lg overflow-hidden">
             <div className="bg-purple-50 p-3 border-b flex justify-between items-center">
              <span className="font-semibold text-purple-700">Remote Version (Incoming)</span>
            </div>
            <ScrollArea className="flex-1 bg-white p-4">
              <pre className="text-xs font-mono whitespace-pre-wrap">{conflict.remoteContent}</pre>
            </ScrollArea>
             <div className="p-3 bg-gray-50 border-t">
              <Button className="w-full bg-purple-600 hover:bg-purple-700" onClick={() => onResolve('remote')}>
                Keep Remote
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter className="sm:justify-between">
           <div className="text-xs text-muted-foreground flex items-center">
             * This action will overwrite the target file immediately.
           </div>
           <Button variant="outline" onClick={onClose}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
