import React, { useState } from 'react';
import ChatWindow from '../components/ChatWindow';
import DocumentPageModal from '../components/DocumentPageModal';

export default function ChatPage({
  activeSessionId = 'new',
  sessions = [],
  draftSession = null,
  onSelectSession,
  onCreateSession,
  onRenameSession,
  onDeleteSession,
  onUpdateSessionScope,
  onSessionActivity,
  activeDocId = 'all',
  documents = [],
  onSelectDoc,
  onNavigateTab,
  isAnswering,
  setIsAnswering,
  isSidebarCollapsed,
  onToggleSidebar
}) {
  const [modalState, setModalState] = useState({
    isOpen: false,
    page: 1,
    docId: null,
    filename: ''
  });

  const handleOpenPageModal = (pageDocId, pageNum, filename) => {
    let targetDocId = pageDocId;
    let targetFilename = filename;
    if (!targetDocId || targetDocId === 'all') {
      if (filename && Array.isArray(documents) && documents.length > 0) {
        const found = documents.find((d) => d.filename === filename);
        if (found) {
          targetDocId = found.doc_id;
          targetFilename = found.filename;
        }
      }
      if (!targetDocId && Array.isArray(documents) && documents.length > 0) {
        targetDocId = documents[0].doc_id;
        targetFilename = documents[0].filename;
      }
    }

    if (targetDocId) {
      const page = pageNum || 1;
      setModalState({
        isOpen: true,
        docId: targetDocId,
        page: page,
        filename: targetFilename || 'Document'
      });
    }
  };

  const handleClosePageModal = () => {
    setModalState((prev) => ({ ...prev, isOpen: false }));
  };

  const activeSession =
    (activeSessionId !== 'new' && sessions.find((s) => s.id === activeSessionId)) ||
    (draftSession && draftSession.id === activeSessionId ? draftSession : null) || {
      id: 'new',
      title: 'New chat',
      scope: 'all',
      file_id: null,
      file_name: 'All files',
      is_file_deleted: false,
      message_count: 0
    };

  return (
    <div className="flex-1 min-h-0 flex flex-col h-full w-full p-2 sm:p-3 overflow-hidden">
      {/* Main Chat Window (Expands to full available screen space) */}
      <div className="flex-1 min-w-0 h-full overflow-hidden flex flex-col">
        <ChatWindow
          activeSessionId={activeSessionId}
          activeSession={activeSession}
          documents={documents}
          sessions={sessions}
          onSelectSession={onSelectSession}
          onCreateSession={onCreateSession}
          onUpdateSessionScope={onUpdateSessionScope}
          onRenameSession={onRenameSession}
          onDeleteSession={onDeleteSession}
          onNavigateTab={onNavigateTab}
          onLoadingChange={setIsAnswering}
          onViewPage={handleOpenPageModal}
          onSessionActivity={onSessionActivity}
          isSidebarCollapsed={isSidebarCollapsed}
          onToggleSidebar={onToggleSidebar}
        />
      </div>

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
