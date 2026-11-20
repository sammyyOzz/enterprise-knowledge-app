"use client";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  streaming: boolean;
}

export function Composer({ value, onChange, onSend, onStop, streaming }: Props) {
  const canSend = value.trim().length > 0 && !streaming;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSend();
      }}
      className="border-t border-rule bg-paper px-5 py-4 md:px-10"
    >
      <div className="mx-auto flex max-w-3xl items-end gap-3">
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (canSend) onSend();
            }
          }}
          rows={1}
          maxLength={2000}
          placeholder="Ask a question about your documents"
          className="field-sizing-content max-h-40 min-h-11 flex-1 resize-none rounded-md border border-rule bg-surface px-3 py-2.5"
        />
        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            className="h-11 rounded-md border border-rule bg-surface px-4 font-medium hover:border-muted"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            className="h-11 rounded-md bg-accent px-5 font-medium text-accent-ink hover:opacity-90 disabled:opacity-40"
          >
            Ask
          </button>
        )}
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-sm text-muted">Enter to send, Shift+Enter for a new line.</p>
    </form>
  );
}