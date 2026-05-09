import {
  Landmark, UtensilsCrossed, Coffee, Trees, Waves, ShoppingBag, Drama,
  Moon, Church, TreePine, Mountain, Hotel, Bus, MapPin, type LucideIcon,
} from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
  museum: Landmark,
  landmark: Landmark,
  restaurant: UtensilsCrossed,
  cafe: Coffee,
  park: Trees,
  beach: Waves,
  shopping: ShoppingBag,
  entertainment: Drama,
  nightlife: Moon,
  religious: Church,
  nature: TreePine,
  viewpoint: Mountain,
  hotel: Hotel,
  transport: Bus,
  other: MapPin,
};

interface Props {
  category: string;
  size?: number;
  className?: string;
}

export default function CategoryIcon({ category, size = 14, className }: Props) {
  const Icon = ICONS[category] || MapPin;
  return <Icon size={size} className={className} />;
}
