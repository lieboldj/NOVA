import React, { useState } from "react";
import { Modal } from "./components";
import NaturalLanguageStarter from "./NaturalLanguageStarter";

export default function ProcessStarter({ onClose, onOpenReview, onChanged }) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      title="Who should receive an MDF request?"
      onClose={onClose}
      busy={busy}
    >
      <NaturalLanguageStarter
        onChanged={onChanged}
        onOpenReview={onOpenReview}
        onBusyChange={setBusy}
      />
    </Modal>
  );
}
