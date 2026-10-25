import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import React from 'react';

interface SheetProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export function Sheet({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
}: SheetProps) {
  return (
    <Dialog.Root open={isOpen} onOpenChange={open => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-slate-950/30 backdrop-blur-sm z-40 transition-opacity animate-in fade-in duration-200" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 h-full w-full sm:max-w-xl md:max-w-2xl border-l border-slate-200 bg-white shadow-2xl flex flex-col focus:outline-none animate-in slide-in-from-right duration-250">
          <div className="flex items-start justify-between px-6 py-5 border-b border-slate-200 bg-white shrink-0">
            <div className="space-y-1.5 pr-6 min-w-0 flex-1">
              {title && <Dialog.Title asChild>{title}</Dialog.Title>}
              {description && <Dialog.Description asChild>{description}</Dialog.Description>}
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="p-2 rounded-lg text-slate-400 hover:text-slate-900 hover:bg-slate-100 transition-colors shrink-0"
                title="Close"
              >
                <X size={18} />
                <span className="sr-only">Close</span>
              </button>
            </Dialog.Close>
          </div>
          
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {children}
          </div>

          {footer && (
            <div className="px-6 py-4 border-t border-slate-200 bg-slate-50/80 shrink-0">
              {footer}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

