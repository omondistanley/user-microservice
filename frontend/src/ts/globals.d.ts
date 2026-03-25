/** Browser globals until scripts use explicit imports. */

export interface PocketiiAuth {
    getToken(): string | null;
    getAccessToken(): string | null;
    getRefreshToken(): string | null;
    getAuthHeaders(): Record<string, string>;
    isLoggedIn(): boolean;
    logout(sessionExpired?: boolean): void;
    refreshAccessToken(): Promise<string>;
    requestWithRefresh(url: string, options?: RequestInit): Promise<Response>;
    login(email: string, password: string): Promise<Record<string, unknown>>;
    fetchGatewayJson(path: string, options?: RequestInit): Promise<unknown>;
    register(
        email: string,
        first_name: string,
        last_name: string,
        password: string
    ): Promise<Record<string, unknown>>;
}

declare global {
    interface Window {
        API_BASE?: string;
        Auth: PocketiiAuth;
    }
}

export {};
