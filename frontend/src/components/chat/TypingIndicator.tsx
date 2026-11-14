import { motion } from "framer-motion";

export function TypingIndicator({ label }: { label?: string }) {
  return (
    <div className="inline-flex items-center gap-2.5 self-start rounded-full border border-hairline bg-surface-card px-4 py-2 shadow-xs">
      <div className="flex items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-teal-deep"
            animate={{ opacity: [0.25, 1, 0.25] }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              delay: i * 0.2,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>
      {label && <span className="font-mono text-[11px] text-stone">{label}</span>}
    </div>
  );
}
