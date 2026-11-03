/**
 * Where a tooltip opens, from its trigger's box and the viewport, as `fixed`
 * offsets. No measuring of the tooltip itself: it opens below unless the room
 * there is short and there is more above, and it hangs from the trigger's
 * right edge when its widest form would run off screen.
 */

/** The gap between trigger and tooltip, and the least margin to the viewport edge, in px. */
const GAP = 8;
const EDGE = 8;
/** The widest a tooltip grows: Tailwind's `max-w-xs`, which `Tooltip` sets. */
export const TOOLTIP_MAX_WIDTH = 320;
/** The room below that a tooltip of a few lines needs before it would rather open upward. */
const MIN_ROOM_BELOW = 160;

export interface TriggerBox {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export interface Viewport {
  width: number;
  height: number;
}

export interface TooltipPlacement {
  top?: number;
  bottom?: number;
  left?: number;
  right?: number;
}

export function placeTooltip(trigger: TriggerBox, viewport: Viewport): TooltipPlacement {
  const roomBelow = viewport.height - trigger.bottom;
  const vertical =
    roomBelow < MIN_ROOM_BELOW && trigger.top > roomBelow
      ? { bottom: viewport.height - trigger.top + GAP }
      : { top: trigger.bottom + GAP };
  const horizontal =
    trigger.left + TOOLTIP_MAX_WIDTH + EDGE > viewport.width
      ? { right: Math.max(EDGE, viewport.width - trigger.right) }
      : { left: trigger.left };
  return { ...vertical, ...horizontal };
}
