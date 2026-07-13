/**
 * Atmospheric depth behind the hero — a layered shadow-fortress / mountain
 * skyline. Pure inline SVG (no raster asset). It is deliberately *barely*
 * visible: near-black layers over deep-red shadow, each blurred, the whole thing
 * masked so its top dissolves into the background (no horizon line). It adds
 * depth, never decoration — the hero text stays the focus.
 *
 * Three parallaxless layers (back → front) give parallax-free depth via
 * decreasing blur + increasing darkness. Responsive: the SVG stretches to the
 * full width and anchors to the bottom, so it reads on every screen size.
 */
export function HeroSilhouette() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-x-0 bottom-0 h-[46vh] min-h-[280px] overflow-hidden"
      style={{
        // Dissolve the top so there is no hard edge / horizon line.
        WebkitMaskImage: 'linear-gradient(to top, #000 0%, #000 34%, transparent 82%)',
        maskImage: 'linear-gradient(to top, #000 0%, #000 34%, transparent 82%)',
        opacity: 0.75,
      }}
    >
      {/* faint deep-red band low on the horizon — light behind the fortress */}
      <div
        className="absolute inset-x-0 bottom-0 h-2/3"
        style={{ background: 'radial-gradient(120% 100% at 50% 100%, rgba(90,0,0,0.16), transparent 70%)' }}
      />

      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 1440 520"
        preserveAspectRatio="none"
        fill="none"
      >
        {/* back ridge — distant peaks, deep red, softest */}
        <path
          d="M0,520 L0,300 L120,340 L260,250 L420,320 L560,230 L720,300 L880,240 L1040,312 L1200,250 L1320,300 L1440,268 L1440,520 Z"
          fill="#3B0000"
          opacity="0.5"
          style={{ filter: 'blur(4px)' }}
        />
        {/* mid ridge — fortress skyline (towers / crenellations) */}
        <path
          d="M0,520 L0,384 L90,384 L90,344 L150,344 L150,392 L240,392 L300,300 L360,392 L470,392 L470,352 L520,352 L520,396 L640,396 L700,322 L760,396 L900,396 L900,360 L950,360 L950,400 L1080,400 L1140,342 L1200,400 L1320,400 L1320,372 L1370,372 L1370,406 L1440,406 L1440,520 Z"
          fill="#220000"
          opacity="0.62"
          style={{ filter: 'blur(2.5px)' }}
        />
        {/* front ridge — closest, near-black, grounds the base */}
        <path
          d="M0,520 L0,432 L180,470 L360,420 L560,460 L760,410 L980,456 L1200,416 L1440,450 L1440,520 Z"
          fill="#050506"
          opacity="0.9"
          style={{ filter: 'blur(1px)' }}
        />
      </svg>
    </div>
  );
}
