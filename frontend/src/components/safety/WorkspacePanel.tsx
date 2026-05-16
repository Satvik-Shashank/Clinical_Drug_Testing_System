import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { InputPanel } from "./InputPanel";
import { ClinicalChat } from "./ClinicalChat";
import { ModeToggle, type InputMode } from "./ModeToggle";
import type { SafetyCheckRequest, SafetyCheckResponse } from "@/lib/safety-types";

interface Props {
  loading: boolean;
  onSubmit: (req: SafetyCheckRequest) => void;
  onReset: () => void;
  onChatResult: (req: SafetyCheckRequest, res: SafetyCheckResponse) => void;
}

export function WorkspacePanel({ loading, onSubmit, onReset, onChatResult }: Props) {
  const [mode, setMode] = useState<InputMode>("form");

  return (
    <div className="space-y-3">
      <ModeToggle mode={mode} onChange={setMode} />
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={mode}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
        >
          {mode === "form" ? (
            <InputPanel loading={loading} onSubmit={onSubmit} onReset={onReset} />
          ) : (
            <ClinicalChat onPromoteToCase={onChatResult} />
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
