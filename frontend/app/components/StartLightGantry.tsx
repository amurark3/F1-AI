/**
 * Backend warm-up stages, in the order the server runs them (`WARMUP_STEPS` in
 * backend/app/services/readiness.py). The index drives how many start lights
 * are illuminated, so the gantry fills as real work completes rather than
 * animating on a timer. A container that has not answered yet lights the first.
 */
const STAGE_ORDER: readonly string[] = ["pending", "database", "model", "season", "store"];
const LIGHT_COUNT = 5;

export function litCountForStage(stage: string | null): number {
  const index = stage ? STAGE_ORDER.indexOf(stage) : -1;
  return Math.min(LIGHT_COUNT, Math.max(1, index + 1));
}

const LAMP_SIZE = "h-4 w-4 sm:h-5 sm:w-5 short:h-4 short:w-4";
const LIT_GLOW = { boxShadow: "0 0 10px rgba(225, 6, 0, 0.6)" };

function Lamp({ lit, out }: { lit: boolean; out: boolean }) {
  if (out) {
    return (
      <span
        className={`${LAMP_SIZE} rounded-full bg-[#E10600] animate-lights-out motion-reduce:animate-none`}
        style={LIT_GLOW}
      />
    );
  }

  return (
    <span
      className={`${LAMP_SIZE} rounded-full transition-colors ${
        lit ? "bg-[#E10600] animate-light-on motion-reduce:animate-none" : "border border-[#232C3D] bg-[#1A2130]"
      }`}
      style={lit ? LIT_GLOW : undefined}
    />
  );
}

interface StartLightGantryProps {
  /** How many of the five columns are lit. */
  lit: number;
  /** Lights out: every lamp goes dark at once. */
  out: boolean;
  label: string;
}

/**
 * Five-column F1 start gantry used as a progress indicator. The newest lit
 * column pulses so a long stage still reads as alive, not frozen.
 */
export default function StartLightGantry({ lit, out, label }: StartLightGantryProps) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={LIGHT_COUNT}
      aria-valuenow={out ? LIGHT_COUNT : lit}
      className="inline-flex items-center gap-2 rounded-lg border border-[#1E2633] bg-[#080B11] px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3 short:py-2"
    >
      {Array.from({ length: LIGHT_COUNT }, (_, index) => {
        const isLit = index < lit;
        const isNewest = !out && index === lit - 1;
        return (
          <span
            key={index}
            className={`flex flex-col gap-1.5 rounded-md bg-[#05070B] p-1.5 ${
              isNewest ? "animate-glow-pulse motion-reduce:animate-none" : ""
            }`}
          >
            <Lamp lit={isLit} out={out} />
            <Lamp lit={isLit} out={out} />
          </span>
        );
      })}
    </div>
  );
}
