import { createBrowserRouter } from "react-router";
import { Layout } from "@/modules/layout";
import { LandingPage } from "@/modules/landing";
import { AuthPage, YandexCallbackPage } from "@/modules/auth";
import { ChatPage } from "@/modules/chat";
import { FavoritesPage } from "@/modules/favorites";
import { QuestionnairePage } from "@/modules/questionnaire";
import { TripsPage, TripDetailPage } from "@/modules/trips";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: LandingPage },
      { path: "login", Component: AuthPage },
      { path: "favorites", Component: FavoritesPage },
      { path: "trips", Component: TripsPage },
      { path: "trips/:tripId", Component: TripDetailPage },
    ],
  },
  {
    path: "/auth/yandex/callback",
    Component: YandexCallbackPage,
  },
  {
    path: "/chat",
    Component: ChatPage,
  },
  {
    path: "/questionnaire",
    Component: QuestionnairePage,
  },
]);
