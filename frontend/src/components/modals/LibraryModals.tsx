import { Modal } from '../ui/Modal';
import { Loader2 } from 'lucide-react';
import { useTranslation } from '../../lib/i18n';
import { AddSourceModal } from './AddSourceModal';
import { AddProfileModal } from './AddProfileModal';
import { AddFromGlobalModal } from './AddFromGlobalModal';

import type { FormEvent } from 'react';
import type { Library } from '../../lib/api-types';

export interface LibraryModalsProps {
  activeLibrary: Library | null;
  isNewLibraryOpen: boolean;
  setIsNewLibraryOpen: (open: boolean) => void;
  newLibraryName: string;
  setNewLibraryName: (name: string) => void;
  handleCreateLibrary: (e: FormEvent) => void;
  isSubmitting: boolean;
  isAddSourceOpen: boolean;
  setIsAddSourceOpen: (open: boolean) => void;
  isAddProfileOpen: boolean;
  setIsAddProfileOpen: (open: boolean) => void;
  isUploadZipOpen: boolean;
  setIsUploadZipOpen: (open: boolean) => void;
  setSelectedFile: (file: File | null) => void;
  selectedFile: File | null;
  handleUploadZip: (e: FormEvent) => void;
  isAddFromGlobalOpen: boolean;
  setIsAddFromGlobalOpen: (open: boolean) => void;
  onContentLinked: () => void;
}

export function LibraryModals({
  activeLibrary,
  isNewLibraryOpen, setIsNewLibraryOpen, newLibraryName, setNewLibraryName, handleCreateLibrary, isSubmitting,
  isAddSourceOpen, setIsAddSourceOpen,
  isAddProfileOpen, setIsAddProfileOpen,
  isUploadZipOpen, setIsUploadZipOpen, setSelectedFile, selectedFile, handleUploadZip,
  isAddFromGlobalOpen, setIsAddFromGlobalOpen,
  onContentLinked
}: LibraryModalsProps) {
  const { t } = useTranslation();

  return (
    <>
      <Modal 
        isOpen={isNewLibraryOpen} 
        onClose={() => setIsNewLibraryOpen(false)} 
        title={t('modal.createLibrary')}
      >
        <form onSubmit={handleCreateLibrary} className="space-y-4">
          <div>
            <label htmlFor="field-librarymodals-52" className="block text-sm font-medium mb-1">{t('modal.libraryName')}</label>
            <input id="field-librarymodals-52" 
              type="text"
             
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
              value={newLibraryName}
              onChange={e => setNewLibraryName(e.target.value)}
              placeholder={t('modal.libraryPlaceholder')}
            />
          </div>
          <div className="flex justify-end gap-2 mt-6">
            <button type="button" onClick={() => setIsNewLibraryOpen(false)} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-md cursor-pointer">{t('modal.cancel')}</button>
            <button type="submit" disabled={isSubmitting || !newLibraryName.trim()} className="px-4 py-2 text-sm bg-slate-900 text-white rounded-md hover:bg-slate-800 disabled:opacity-50 flex items-center gap-2 cursor-pointer">
              {isSubmitting && <Loader2 size={14} className="animate-spin" />}
              {isSubmitting ? t('modal.creating') : t('modal.create')}
            </button>
          </div>
        </form>
      </Modal>

      <AddSourceModal 
        isOpen={isAddSourceOpen} 
        onClose={() => setIsAddSourceOpen(false)} 
        activeLibrary={activeLibrary} 
      />

      <AddProfileModal 
        isOpen={isAddProfileOpen} 
        onClose={() => setIsAddProfileOpen(false)} 
        activeLibrary={activeLibrary} 
      />

      <AddFromGlobalModal
        isOpen={isAddFromGlobalOpen}
        onClose={() => setIsAddFromGlobalOpen(false)}
        activeLibrary={activeLibrary}
        onSuccess={onContentLinked}
      />

      <Modal 
        isOpen={isUploadZipOpen} 
        onClose={() => setIsUploadZipOpen(false)} 
        title={t('modal.uploadZipTitle')}
      >
        <form onSubmit={handleUploadZip} className="space-y-4">
          <p className="text-sm text-gray-500">{t('modal.uploadZipDesc')}</p>
          <div>
            <input aria-label={t('addProfile.uploadCookies')} 
              type="file"
              accept=".zip,.json"
              className="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-slate-50 file:text-slate-900 hover:file:bg-slate-100 cursor-pointer"
              onChange={e => setSelectedFile(e.target.files?.[0] || null)}
            />
          </div>
          <div className="flex justify-end gap-2 mt-6">
            <button type="button" onClick={() => setIsUploadZipOpen(false)} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-md cursor-pointer">{t('modal.cancel')}</button>
            <button type="submit" disabled={isSubmitting || !selectedFile} className="px-4 py-2 text-sm bg-slate-900 text-white rounded-md hover:bg-slate-800 disabled:opacity-50 flex items-center gap-2 cursor-pointer">
              {isSubmitting && <Loader2 size={14} className="animate-spin" />}
              {t('modal.uploadBtn')}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}
