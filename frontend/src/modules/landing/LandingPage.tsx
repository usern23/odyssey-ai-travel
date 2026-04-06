import { HeroSection } from './HeroSection';
import { DestinationsGrid } from './DestinationsGrid';
import { CTASection } from './CTASection';

export default function LandingPage() {
  return (
    <div className="w-full">
      <HeroSection />
      <DestinationsGrid />
      <CTASection />
    </div>
  );
}
