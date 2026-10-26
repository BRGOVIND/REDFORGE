import { useCallback, useRef, useState } from 'react';
import { Entry } from './components/Entry';
import { Nav } from './components/Nav';
import { WorkbenchPreview } from './sections/WorkbenchPreview';
import { Hero } from './sections/Hero';
import { Capabilities } from './sections/Capabilities';
import { Problem } from './sections/Problem';
import { Vision } from './sections/Vision';
import { Pipeline } from './sections/Pipeline';
import { AttackViz } from './sections/AttackViz';
import { Benchmark } from './sections/Benchmark';
import { Stack } from './sections/Stack';
import { BuiltFor } from './sections/BuiltFor';
import { Local } from './sections/Local';
import { QuickInstall } from './sections/QuickInstall';
import { Download } from './sections/Download';
import { InstallSteps } from './sections/InstallSteps';
import { Future } from './sections/Future';
import { About } from './sections/About';
import { Footer } from './components/Footer';
import { ForgeCursor } from './components/ForgeCursor';

export default function App() {
  const [entered, setEntered] = useState(false);
  const logoRef = useRef<HTMLDivElement>(null);
  const finishEntry = useCallback(() => setEntered(true), []);

  const replayEntry = () => {
    history.replaceState(null, "", location.pathname + location.search);
    window.scrollTo({ top: 0, behavior: "instant" });
    setEntered(false);
  };

  return (
    <div className="grain landing-light relative min-h-screen">
      <Nav visible={entered} logoRef={logoRef} onReplay={replayEntry} />
      {!entered && <Entry logoRef={logoRef} onDone={finishEntry} />}
      <main>
        <Hero started={entered} />
        <WorkbenchPreview />
        <Capabilities />
        <Pipeline />
        <Problem />
        <AttackViz />
        <Benchmark />
        <Stack />
        <BuiltFor />
        <Future />
        <Local />
        <Download />
        <InstallSteps />
        <QuickInstall />
        <Vision />
        <About />
      </main>
      <Footer />
      <ForgeCursor />
    </div>
  );
}
