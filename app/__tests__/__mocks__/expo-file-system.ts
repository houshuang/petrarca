export const Paths = {
  document: "/mock/documents",
  cache: "/mock/cache",
};

export class File {
  uri: string;
  constructor(uri: string) {
    this.uri = uri;
  }
  exists = false;
  text = "";
  create() {
    this.exists = true;
  }
  write(content: string) {
    this.text = content;
    this.exists = true;
  }
}

export class Directory {
  uri: string;
  constructor(uri: string) {
    this.uri = uri;
  }
  exists = false;
  create() {
    this.exists = true;
  }
}
