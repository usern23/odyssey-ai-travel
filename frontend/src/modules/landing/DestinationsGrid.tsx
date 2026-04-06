import { motion } from 'motion/react';
import { Link } from 'react-router';
import { MapPin, ArrowRight } from 'lucide-react';
import { ImageWithFallback } from '@/shared/components/ImageWithFallback';

const destinations = [
  { name: 'Токио', country: 'Япония', img: 'https://images.unsplash.com/photo-1578880711168-af090bacce15?q=80&w=600', tag: 'Культура' },
  { name: 'Мальдивы', country: 'Индийский океан', img: 'https://images.unsplash.com/photo-1771767642966-b9e8d3dd9e7f?q=80&w=600', tag: 'Пляж' },
  { name: 'Церматт', country: 'Швейцария', img: 'https://images.unsplash.com/photo-1595368062405-e4d7840cba14?q=80&w=600', tag: 'Горы' },
  { name: 'Тулум', country: 'Мексика', img: 'https://images.unsplash.com/photo-1766329808475-9d6aa3dd15d7?q=80&w=600', tag: 'Отдых' },
];

export function DestinationsGrid() {
  return (
    <section className="py-24 bg-white dark:bg-[#0A0A0A]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-end justify-between mb-12">
          <div>
            <h2 className="text-3xl font-bold text-slate-900 dark:text-white mb-4">
              Популярные направления
            </h2>
            <p className="text-slate-600 dark:text-slate-400 text-lg">
              Вдохновитесь готовыми идеями для вашего следующего отпуска
            </p>
          </div>
          <Link
            to="/favorites"
            className="hidden sm:flex items-center gap-1 text-blue-600 dark:text-blue-400 font-semibold hover:gap-2 transition-all"
          >
            Смотреть все <ArrowRight size={18} />
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {destinations.map((dest, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              className="group relative rounded-3xl overflow-hidden aspect-[4/5] cursor-pointer shadow-md"
            >
              <ImageWithFallback
                src={dest.img}
                alt={dest.name}
                className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-slate-900/90 via-slate-900/20 to-transparent" />
              <div className="absolute top-4 left-4">
                <span className="px-3 py-1.5 bg-white/20 backdrop-blur-md text-white text-xs font-semibold rounded-full border border-white/30">
                  {dest.tag}
                </span>
              </div>
              <div className="absolute bottom-0 left-0 p-6 w-full">
                <h3 className="text-2xl font-bold text-white mb-1">{dest.name}</h3>
                <div className="flex items-center text-slate-300 text-sm gap-1.5">
                  <MapPin size={14} /> {dest.country}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
