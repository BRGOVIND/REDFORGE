import { useCallback, useRef, useState } from 'react';
import { Entry } from './components/Entry';
import { Nav } from './components/Nav';
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

export default function App() {
  const [entered, setEntered] = useState(false);
  const logoRef = useRef<HTMLDivElement>(null);
  const finishEntry = useCallback(() => setEntered(true), []);

  return (
    <div className="grain landing-light relative min-h-screen">
      <Nav visible={entered} logoRef={logoRef} />
      {!entered && <Entry logoRef={logoRef} onDone={finishEntry} />}
      <main>
        <Hero started={entered} />
        <Capabilities />
        <Pipeline />
        <Problem />
        <AttackViz />
        <Benchmark />
        <Stack />
        <BuiltFor />
        <Local />
        <QuickInstall />
        <Download />
        <InstallSteps />
        <Vision />
        <Future />
        <About />
      </main>
      <Footer />
    </div>
  );
}
