"use client";

import {
  FormEvent,
  ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  AuthState,
  getCurrentAuth,
  login,
  logout,
} from "@/lib/api";
import { Dashboard } from "@/components/dashboard";
import { PlatformDashboard } from "@/components/platform-dashboard";
import { LogoMark } from "@/components/icons";

export function AuthenticatedApp() {
  const [auth, setAuth] =
    useState<AuthState | null | undefined>(undefined);
  const [selectedStoreId, setSelectedStoreId] =
    useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getCurrentAuth()
      .then(setAuth)
      .catch((requestError) => {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Não foi possível verificar sua sessão.",
        );
        setAuth(null);
      });
  }, []);

  const stores = useMemo(
    () =>
      auth?.companies.flatMap((company) =>
        company.stores.map((store) => ({
          ...store,
          companyName: company.name,
          role: company.role,
        })),
      ) ?? [],
    [auth],
  );

  useEffect(() => {
    if (!auth || auth.user.is_platform_admin) {
      return;
    }

    const saved =
      localStorage.getItem("smartfoodia.authorizedStoreId");

    const selected =
      stores.find((store) => store.id === saved) ??
      stores[0];

    setSelectedStoreId(selected?.id ?? "");
  }, [auth, stores]);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      localStorage.removeItem(
        "smartfoodia.authorizedStoreId",
      );
      setAuth(null);
      setSelectedStoreId("");
    }
  }

  if (auth === undefined) {
    return (
      <div className="authPage">
        <div className="authLoading">
          <LogoMark size={52} />
          <strong>SmartFoodIA</strong>
          <span>Carregando sua sessão...</span>
        </div>
      </div>
    );
  }

  if (!auth) {
    return (
      <LoginScreen
        initialError={error}
        onAuthenticated={(nextAuth) => {
          setError(null);
          setAuth(nextAuth);
        }}
      />
    );
  }

  if (auth.user.is_platform_admin) {
    return (
      <SessionFrame
        auth={auth}
        onLogout={handleLogout}
      >
        <PlatformDashboard />
      </SessionFrame>
    );
  }

  const selectedStore = stores.find(
    (store) => store.id === selectedStoreId,
  );

  return (
    <SessionFrame
      auth={auth}
      onLogout={handleLogout}
    >
      {stores.length === 0 ? (
        <div className="authPage">
          <div className="authCard">
            <h1>Nenhuma loja disponível</h1>
            <p>
              Seu usuário está autenticado, mas ainda não possui
              uma loja ativa vinculada.
            </p>
          </div>
        </div>
      ) : selectedStore ? (
        <>
          {stores.length > 1 && (
            <div className="tenantSelector">
              <label htmlFor="authorized-store">
                Loja
              </label>
              <select
                id="authorized-store"
                value={selectedStoreId}
                onChange={(event) => {
                  const nextId = event.target.value;
                  setSelectedStoreId(nextId);
                  localStorage.setItem(
                    "smartfoodia.authorizedStoreId",
                    nextId,
                  );
                }}
              >
                {stores.map((store) => (
                  <option
                    key={store.id}
                    value={store.id}
                  >
                    {store.companyName} — {store.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <Dashboard
            initialStoreId={selectedStore.id}
            lockStore
            storeLabel={selectedStore.name}
          />
        </>
      ) : null}
    </SessionFrame>
  );
}

function LoginScreen({
  onAuthenticated,
  initialError,
}: {
  onAuthenticated: (auth: AuthState) => void;
  initialError: string | null;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] =
    useState<string | null>(initialError);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const result = await login(email, password);
      onAuthenticated(result);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível entrar.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="authPage">
      <div className="authCard">
        <div className="authBrand">
          <LogoMark size={48} />
          <div>
            <strong>SmartFoodIA</strong>
            <span>Central operacional</span>
          </div>
        </div>

        <div className="authHeading">
          <p className="eyebrow">ACESSO SEGURO</p>
          <h1>Entrar no painel</h1>
          <p>
            Use o usuário da sua empresa para acessar
            somente as operações autorizadas.
          </p>
        </div>

        <form
          className="authForm"
          onSubmit={submit}
        >
          <label htmlFor="login-email">
            E-mail
          </label>
          <input
            id="login-email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) =>
              setEmail(event.target.value)
            }
          />

          <label htmlFor="login-password">
            Senha
          </label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            required
            minLength={8}
            value={password}
            onChange={(event) =>
              setPassword(event.target.value)
            }
          />

          {error && (
            <div className="authError">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
          >
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}

function SessionFrame({
  auth,
  onLogout,
  children,
}: {
  auth: AuthState;
  onLogout: () => void;
  children: ReactNode;
}) {
  return (
    <>
      {children}

      <div className="sessionBadge">
        <div>
          <strong>{auth.user.name}</strong>
          <span>{auth.user.email}</span>
        </div>
        <button
          type="button"
          onClick={() => void onLogout()}
        >
          Sair
        </button>
      </div>
    </>
  );
}
