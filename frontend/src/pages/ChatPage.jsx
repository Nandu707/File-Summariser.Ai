import React, { useState } from 'react';
import ChatWindow from '../components/ChatWindow';
import DocumentPageModal from '../components/DocumentPageModal';

export default function ChatPage({
  activeDocId = 'all',
  documents = [],
  onSelectDoc,
  onNavigateTab,
  isAnswering,
  setIsAnswering
}) {
  const [modalState, setModalState] = useState({
    isOpen: false,
    page: 1,
    docId: null,
    filename: ''
  });

  const handleOpenPageModal = (pageDocId, pageNum, filename) => {
    setModalState({
      isOpen: true,
      page: pageNum || 1,
      docId: pageDocId,
      filename: filename || 'Document'
    });
  };

  const handleClosePageModal = () => {
    setModalState((prev) => ({ ...prev, isOpen: false }));
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col h-full max-w-6xl w-full mx-auto p-3 sm:p-5 lg:p-6">
      {/* Dedicated Chat Window */}
      <ChatWindow
        activeDocId={activeDocId}
        documents={documents}
        onSelectDoc={onSelectDoc}
        onNavigateTab={onNavigateTab}
        onLoadingChange={setIsAnswering}
        onViewPage={handleOpenPageModal}
      />

      {/* Document Page Modal for viewing cited source pages & documents */}
      <DocumentPageModal
        isOpen={modalState.isOpen}
        onClose={handleClosePageModal}
        docId={modalState.docId}
        initialPage={modalState.page}
        filename={modalState.filename}
      />
    </div>
  );
}
